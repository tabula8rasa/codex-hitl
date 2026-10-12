"""RAM-only requests, serialized by one asyncio event loop."""
import asyncio
import logging
from asyncio import timeout, wait_for
from dataclasses import dataclass
from uuid import uuid4

import httpx

from codex_hitl.auth import internal_headers
from codex_hitl.config import MCPConfig
from codex_hitl.contracts import (
    AnswerRequest, Decision, ExpiryNotification, ExpiryResponse, Message, MessageResponse, Request, RequestType,
    TextAnswer, TimeoutResult, answer_matches,
)

RESPONSE_WAIT_SECONDS = 850
DELIVERY_BUDGET_SECONDS = 10
EXPIRY_BUDGET_SECONDS = 10
logger = logging.getLogger(__name__)


class DeliveryError(RuntimeError):
    """Delivery failed or its outcome is unknown. Never retry automatically."""


@dataclass
class PendingRequest:
    future: asyncio.Future
    request_type: RequestType


class RequestService:
    def __init__(self, config: MCPConfig, client: httpx.AsyncClient):
        self.config = config
        self.client = client
        self.pending: dict[str, PendingRequest] = {}

    def receive_answer(self, answer: AnswerRequest) -> bool:
        # No await may be introduced between this check and set_result. One
        # event loop makes first-response acceptance atomic, including when
        # the original caller has not yet run its finally block.
        entry = self.pending.get(answer.request_id)
        if entry is None or entry.future.done():
            return False
        if not answer_matches(entry.request_type, answer.answer):
            return False
        entry.future.set_result(answer.answer)
        return True

    async def request(self, request: Request) -> dict:
        request_id = str(uuid4())
        entry = PendingRequest(asyncio.get_running_loop().create_future(), request.type)
        self.pending[request_id] = entry
        message = Message(request_id=request_id, **request.model_dump())
        try:
            try:
                # httpx timeouts alone are per-operation; this context bounds
                # the entire delivery, including a slow streaming response.
                async with timeout(DELIVERY_BUDGET_SECONDS):
                    response = await self.client.post(
                        self.config.bot_api_url.rstrip("/") + "/internal/messages",
                        json=message.model_dump(),
                        headers=internal_headers(self.config.internal_api_token),
                        timeout=DELIVERY_BUDGET_SECONDS,
                    )
                    response.raise_for_status()
                    delivered = MessageResponse.model_validate(response.json())
            except Exception:
                # Do not expose response bodies, URLs or credentials in tool errors.
                raise DeliveryError("HITL message delivery failed; outcome may be unknown") from None
            try:
                result: Decision | TextAnswer = await wait_for(entry.future, RESPONSE_WAIT_SECONDS)
                return result.model_dump()
            except TimeoutError:
                # Expiry is terminal before any external await: a racing answer
                # must be rejected even while Telegram editing is in progress.
                if self.pending.get(request_id) is entry:
                    del self.pending[request_id]
                if not entry.future.done():
                    entry.future.cancel()
                await self.notify_expiry(ExpiryNotification(message_id=delivered.message_id, message=message))
                return TimeoutResult().model_dump()
        finally:
            if self.pending.get(request_id) is entry:
                del self.pending[request_id]
            if not entry.future.done():
                entry.future.cancel()

    async def notify_expiry(self, notification: ExpiryNotification) -> None:
        try:
            async with timeout(EXPIRY_BUDGET_SECONDS):
                response = await self.client.post(
                    self.config.bot_api_url.rstrip("/") + "/internal/expire",
                    json=notification.model_dump(),
                    headers=internal_headers(self.config.internal_api_token),
                    timeout=EXPIRY_BUDGET_SECONDS,
                )
                response.raise_for_status()
                ExpiryResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, TimeoutError):
            logger.warning("HITL expiry notification failed")

    def shutdown(self) -> None:
        for entry in self.pending.values():
            if not entry.future.done():
                entry.future.cancel()
        self.pending.clear()
