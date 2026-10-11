"""Stateless request correlation through bot-authored Telegram messages."""
import asyncio
import logging
from uuid import UUID

import httpx

from codex_hitl.auth import internal_headers
from codex_hitl.config import BotConfig
from codex_hitl.contracts import Acceptance, AnswerRequest, Message

logger = logging.getLogger(__name__)
ACTIONS = {
    "approve": ("approval", "approved"),
    "reject": ("approval", "rejected"),
    "done": ("manual_action", "completed"),
    "unable": ("manual_action", "unable"),
}


class TelegramError(Exception):
    """Safe operational error; never expose credential-bearing HTTP URLs."""


def parse_marker(text: object) -> tuple[str, str] | None:
    if not isinstance(text, str):
        return None
    first = text.split("\n", 1)[0]
    parts = first.split(" ")
    if len(parts) != 3 or parts[0] != "HITL" or parts[2] not in {"approval", "question", "manual_action"}:
        return None
    try:
        parsed = UUID(parts[1])
    except ValueError:
        return None
    if parsed.version != 4 or str(parsed) != parts[1]:
        return None
    return parts[1], parts[2]


def render_message(message: Message, chat_id: int) -> dict:
    text = f"HITL {message.request_id} {message.type}\n\n{message.title}\n\n{message.description}"
    payload = {"chat_id": chat_id, "text": text}
    if message.type == "question":
        payload["text"] += "\n\nReply directly to this message with your text answer."
    else:
        labels = (("Approve", "approve"), ("Reject", "reject")) if message.type == "approval" else (("Done", "done"), ("Unable", "unable"))
        payload["reply_markup"] = {"inline_keyboard": [[
            {"text": label, "callback_data": f"{action}:{message.request_id}"} for label, action in labels
        ]]}
    return payload


class TelegramBot:
    def __init__(self, config: BotConfig, telegram_client: httpx.AsyncClient, mcp_client: httpx.AsyncClient, *, telegram_api_url: str = "https://api.telegram.org"):
        self.config = config
        self.telegram_client = telegram_client
        self.mcp_client = mcp_client
        self.api_url = f"{telegram_api_url.rstrip('/')}/bot{config.telegram_bot_token}"
        self.bot_id: int | None = None
        self.offset: int | None = None
        self.polling_task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()

    async def telegram(self, method: str, payload: dict, *, polling: bool = False):
        try:
            async with asyncio.timeout(40 if polling else 10):
                response = await self.telegram_client.post(f"{self.api_url}/{method}", json=payload, timeout=40 if polling else 10)
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or body.get("ok") is not True or "result" not in body:
                    raise TelegramError("Telegram operation failed")
                return body["result"]
        except (httpx.HTTPError, ValueError, TimeoutError):
            raise TelegramError("Telegram operation failed") from None

    async def initialize(self):
        identity = await self.telegram("getMe", {})
        if not isinstance(identity, dict) or type(identity.get("id")) is not int or identity.get("is_bot") is not True:
            raise TelegramError("Telegram bot identity could not be verified")
        self.bot_id = identity["id"]

    async def start(self):
        async with self._start_lock:
            if self.polling_task is not None:
                raise RuntimeError("Only one Telegram polling task is supported")
            await self.initialize()
            self.polling_task = asyncio.create_task(self.poll_updates(), name="telegram-getUpdates")

    async def stop(self):
        if self.polling_task is not None:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
            self.polling_task = None

    async def send_message(self, message: Message) -> int:
        result = await self.telegram("sendMessage", render_message(message, self.config.telegram_chat_id))
        if not isinstance(result, dict) or type(result.get("message_id")) is not int:
            raise TelegramError("Telegram returned an invalid message identifier")
        return result["message_id"]

    def original_marker(self, message: object) -> tuple[str, str] | None:
        if not isinstance(message, dict) or self.bot_id is None:
            return None
        sender, chat = message.get("from"), message.get("chat")
        if not isinstance(sender, dict) or sender.get("id") != self.bot_id or sender.get("is_bot") is not True:
            return None
        if not isinstance(chat, dict) or chat.get("id") != self.config.telegram_chat_id:
            return None
        if type(message.get("message_id")) is not int:
            return None
        return parse_marker(message.get("text"))

    def authorized(self, sender: object) -> bool:
        return isinstance(sender, dict) and type(sender.get("id")) is int and sender["id"] == self.config.telegram_allowed_user_id

    async def best_effort(self, method: str, payload: dict):
        try:
            await self.telegram(method, payload)
        except TelegramError:
            logger.warning("Telegram %s failed", method)

    async def notify(self, text: str):
        await self.best_effort("sendMessage", {"chat_id": self.config.telegram_chat_id, "text": text})

    async def send_answer_to_mcp(self, request_id: str, answer: dict, message_id: int, *, buttons: bool):
        payload = AnswerRequest(request_id=request_id, answer=answer)
        try:
            async with asyncio.timeout(10):
                response = await self.mcp_client.post(
                    f"{self.config.hitl_api_url.rstrip('/')}/internal/answer",
                    json=payload.model_dump(), headers=internal_headers(self.config.internal_api_token), timeout=10,
                )
                response.raise_for_status()
                accepted = Acceptance.model_validate(response.json()).accepted
        except (httpx.HTTPError, ValueError, TimeoutError):
            logger.warning("Answer forwarding failed")
            await self.notify("Answer delivery failed. Acceptance could not be confirmed; the answer was not retried.")
            return
        if not accepted:
            await self.notify("This request is no longer active. Your answer was not accepted.")
        elif buttons:
            await self.best_effort("editMessageReplyMarkup", {
                "chat_id": self.config.telegram_chat_id, "message_id": message_id,
                "reply_markup": {"inline_keyboard": []},
            })

    async def handle_update(self, update: object):
        if not isinstance(update, dict):
            return
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            if not self.authorized(callback.get("from")):
                return
            original = callback.get("message")
            marker = self.original_marker(original)
            data = callback.get("data")
            if marker is None or not isinstance(data, str):
                return
            action, separator, request_id = data.partition(":")
            if not separator or action not in ACTIONS or marker != (request_id, ACTIONS[action][0]):
                return
            callback_id = callback.get("id")
            if not isinstance(callback_id, str):
                return
            await self.best_effort("answerCallbackQuery", {"callback_query_id": callback_id})
            await self.send_answer_to_mcp(request_id, {"status": ACTIONS[action][1]}, original["message_id"], buttons=True)
            return
        message = update.get("message")
        if not isinstance(message, dict) or not self.authorized(message.get("from")):
            return
        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("id") != self.config.telegram_chat_id:
            return
        marker = self.original_marker(message.get("reply_to_message"))
        if marker is None or not isinstance(message.get("text"), str):
            return
        if marker[1] != "question":
            if type(message.get("message_id")) is int:
                await self.best_effort("deleteMessage", {"chat_id": self.config.telegram_chat_id, "message_id": message["message_id"]})
            return
        await self.send_answer_to_mcp(marker[0], {"status": "answered", "answer": message["text"]}, message["reply_to_message"]["message_id"], buttons=False)

    async def poll_updates(self):
        failures = 0
        while True:
            try:
                payload = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
                if self.offset is not None:
                    payload["offset"] = self.offset
                updates = await self.telegram("getUpdates", payload, polling=True)
                if not isinstance(updates, list):
                    raise TelegramError("Invalid Telegram update batch")
                for update in updates:
                    if not isinstance(update, dict) or type(update.get("update_id")) is not int:
                        continue
                    if self.offset is not None and update["update_id"] < self.offset:
                        continue
                    try:
                        await self.handle_update(update)
                    finally:
                        # Consume once even if forwarding failed: no ambiguous-delivery retry.
                        self.offset = update["update_id"] + 1
                failures = 0
            except (TelegramError, httpx.HTTPError, ValueError, TypeError, KeyError):
                failures += 1
                logger.warning("Telegram polling operation failed")
                await asyncio.sleep(min(2 ** min(failures - 1, 5), 30))
