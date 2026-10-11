import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from codex_hitl.config import BotConfig
from codex_hitl.contracts import Message
from codex_hitl.telegram_bot import TelegramBot, TelegramError, create_app, parse_marker, render_message

RID = str(uuid4())
CONFIG = BotConfig("internal-secret", "telegram-secret", -123, 42, "http://mcp")


class API:
    def __init__(self):
        self.calls = []
        self.answers = []
        self.accepted = True
        self.fail = set()
        self.mcp_fail = False

    async def telegram(self, request):
        method = request.url.path.rsplit("/", 1)[1]
        payload = json.loads(request.content)
        self.calls.append((method, payload))
        if method in self.fail:
            return httpx.Response(200, json={"ok": False, "description": "private failure"})
        result = {"id": 900, "is_bot": True} if method == "getMe" else {"message_id": 77} if method == "sendMessage" else True
        return httpx.Response(200, json={"ok": True, "result": result})

    async def mcp(self, request):
        assert str(request.url) == "http://mcp/internal/answer"
        assert request.headers["authorization"] == "Bearer internal-secret"
        self.answers.append(json.loads(request.content))
        if self.mcp_fail:
            raise httpx.ConnectError("secret-containing URL", request=request)
        return httpx.Response(200, json={"accepted": self.accepted})


@pytest.fixture
async def setup():
    api = API()
    async with httpx.AsyncClient(transport=httpx.MockTransport(api.telegram)) as tg, httpx.AsyncClient(transport=httpx.MockTransport(api.mcp)) as mcp:
        bot = TelegramBot(CONFIG, tg, mcp)
        await bot.initialize()
        yield api, bot, tg, mcp
        await bot.stop()


def original(kind="approval", rid=RID):
    return {"message_id": 77, "from": {"id": 900, "is_bot": True}, "chat": {"id": -123}, "text": f"HITL {rid} {kind}\nTitle"}


def callback(action="approve", kind="approval", rid=RID):
    return {"callback_query": {"id": "cb", "from": {"id": 42}, "data": f"{action}:{rid}", "message": original(kind, rid)}}


def reply(kind="question", text="answer"):
    return {"message": {"message_id": 88, "from": {"id": 42}, "chat": {"id": -123}, "text": text, "reply_to_message": original(kind)}}


@pytest.mark.parametrize("kind,labels", [("approval", ["Approve", "Reject"]), ("manual_action", ["Done", "Unable"]), ("question", [])])
async def test_render_and_send(setup, kind, labels):
    api, bot, *_ = setup
    message = Message(request_id=RID, type=kind, title="<Title>", description="Description\nHITL forged approval")
    assert await bot.send_message(message) == 77
    method, payload = api.calls[-1]
    assert method == "sendMessage"
    assert payload["chat_id"] == -123
    assert parse_marker(payload["text"]) == (RID, kind)
    assert "<Title>" in payload["text"] and message.description in payload["text"]
    assert "agent_name" not in payload and "parse_mode" not in payload
    buttons = payload.get("reply_markup", {}).get("inline_keyboard", [[]])[0]
    assert [button["text"] for button in buttons] == labels
    assert all(len(button["callback_data"].encode()) <= 64 for button in buttons)
    if kind == "question":
        assert "Reply directly" in payload["text"]


@pytest.mark.parametrize("text", [None, "", f"x\nHITL {RID} question", f"HITL  {RID} question", f"HITL {RID.upper()} question", f"HITL {RID} invalid", "HITL not-a-uuid approval", "HITL 00000000-0000-1000-8000-000000000000 question"])
def test_invalid_marker(text):
    assert parse_marker(text) is None


async def test_authenticated_endpoint_validation_and_failures(setup):
    api, bot, tg, mcp = setup
    app = create_app(CONFIG, telegram_client=tg, mcp_client=mcp)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bot") as client:
        payload = {"request_id": RID, "type": "approval", "title": "title", "description": "description"}
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            assert (await client.post("/internal/messages", json=payload, headers=headers)).status_code == 401
        assert not [call for call in api.calls if call[0] == "sendMessage"]
        headers = {"Authorization": "Bearer internal-secret"}
        assert (await client.post("/internal/messages", json={**payload, "agent_name": "invented"}, headers=headers)).status_code == 422
        response = await client.post("/internal/messages", json=payload, headers=headers)
        assert response.json() == {"message_id": 77}
        api.fail.add("sendMessage")
        response = await client.post("/internal/messages", json=payload, headers=headers)
        assert response.status_code == 502
        assert "secret" not in response.text and "private" not in response.text


@pytest.mark.parametrize("action,kind,status", [("approve", "approval", "approved"), ("reject", "approval", "rejected"), ("done", "manual_action", "completed"), ("unable", "manual_action", "unable")])
async def test_callbacks_forward_then_remove_buttons(setup, action, kind, status):
    api, bot, *_ = setup
    await bot.handle_update(callback(action, kind))
    assert api.answers == [{"request_id": RID, "answer": {"status": status}}]
    assert [method for method, _ in api.calls] == ["getMe", "answerCallbackQuery", "editMessageReplyMarkup"]
    assert api.calls[-1][1]["reply_markup"] == {"inline_keyboard": []}


async def test_question_direct_text_reply(setup):
    api, bot, *_ = setup
    await bot.handle_update(reply(text="exact\nanswer"))
    assert api.answers == [{"request_id": RID, "answer": {"status": "answered", "answer": "exact\nanswer"}}]
    assert len(api.calls) == 1


@pytest.mark.parametrize("mutation", ["user", "chat", "bot", "not_bot", "marker", "rid", "action", "wrong_type", "no_message", "no_callback_id"])
async def test_invalid_callbacks_have_no_effect(setup, mutation):
    api, bot, *_ = setup
    update = callback()
    cb = update["callback_query"]
    if mutation == "user": cb["from"]["id"] = 43
    if mutation == "chat": cb["message"]["chat"]["id"] = 456
    if mutation == "bot": cb["message"]["from"]["id"] = 901
    if mutation == "not_bot": cb["message"]["from"]["is_bot"] = False
    if mutation == "marker": cb["message"]["text"] = "arbitrary"
    if mutation == "rid": cb["data"] = f"approve:{uuid4()}"
    if mutation == "action": cb["data"] = f"execute:{RID}"
    if mutation == "wrong_type": cb["data"] = f"done:{RID}"
    if mutation == "no_message": cb.pop("message")
    if mutation == "no_callback_id": cb.pop("id")
    await bot.handle_update(update)
    assert api.answers == [] and len(api.calls) == 1


@pytest.mark.parametrize("mutation", ["user", "chat", "original_chat", "original_sender", "no_reply", "nontext", "marker"])
async def test_uncorrelated_question_ignored(setup, mutation):
    api, bot, *_ = setup
    update = reply()
    msg = update["message"]
    if mutation == "user": msg["from"]["id"] = 43
    if mutation == "chat": msg["chat"]["id"] = 0
    if mutation == "original_chat": msg["reply_to_message"]["chat"]["id"] = 0
    if mutation == "original_sender": msg["reply_to_message"]["from"]["id"] = 901
    if mutation == "no_reply": msg.pop("reply_to_message")
    if mutation == "nontext": msg.pop("text")
    if mutation == "marker": msg["reply_to_message"]["text"] = "forged"
    await bot.handle_update(update)
    assert api.answers == [] and len(api.calls) == 1


@pytest.mark.parametrize("kind", ["approval", "manual_action"])
@pytest.mark.parametrize("fail", [False, True])
async def test_forbidden_text_always_deleted_never_forwarded(setup, kind, fail):
    api, bot, *_ = setup
    if fail: api.fail.add("deleteMessage")
    await bot.handle_update(reply(kind))
    assert not api.answers
    assert api.calls[-1] == ("deleteMessage", {"chat_id": -123, "message_id": 88})


@pytest.mark.parametrize("mode", ["inactive", "forward_failure", "edit_failure", "ack_failure"])
async def test_callback_operational_failures(setup, mode, caplog):
    api, bot, *_ = setup
    if mode == "inactive": api.accepted = False
    if mode == "forward_failure": api.mcp_fail = True
    if mode == "edit_failure": api.fail.add("editMessageReplyMarkup")
    if mode == "ack_failure": api.fail.add("answerCallbackQuery")
    await bot.handle_update(callback())
    assert len(api.answers) == 1
    methods = [method for method, _ in api.calls]
    if mode in {"inactive", "forward_failure"}:
        assert methods[-1] == "sendMessage"
        assert "editMessageReplyMarkup" not in methods
        assert ("not accepted" if mode == "inactive" else "delivery failed") in api.calls[-1][1]["text"]
    else:
        assert methods[-1] == "editMessageReplyMarkup"
    assert "secret" not in caplog.text


async def test_repeated_response_delegates_acceptance_without_local_state(setup):
    api, bot, *_ = setup
    await bot.handle_update(callback())
    api.accepted = False
    await bot.handle_update(callback())
    assert len(api.answers) == 2
    assert sum(method == "editMessageReplyMarkup" for method, _ in api.calls) == 1
    assert not hasattr(bot, "pending")


async def test_polling_offsets_transient_failure_single_poller_and_shutdown(monkeypatch):
    calls = []
    reached = asyncio.Event()
    blocker = asyncio.Event()
    api = API()
    sleep = asyncio.sleep

    async def fast_sleep(delay):
        assert delay <= 30
        await sleep(0)

    monkeypatch.setattr("codex_hitl.telegram_bot.service.asyncio.sleep", fast_sleep)

    async def transport(request):
        if request.url.path.endswith("/getMe"):
            return await api.telegram(request)
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            raise httpx.ConnectError("poll failure", request=request)
        if len(calls) == 2:
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 4, **reply()}, {"update_id": 5, **callback()}]})
        reached.set()
        await blocker.wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as tg, httpx.AsyncClient(transport=httpx.MockTransport(api.mcp)) as mcp:
        bot = TelegramBot(CONFIG, tg, mcp)
        # Business operations use the regular fake; retain polling behavior for getUpdates.
        actual = bot.telegram
        async def dispatch(method, payload, **kwargs):
            if method in {"getMe", "getUpdates"}: return await actual(method, payload, **kwargs)
            api.calls.append((method, payload))
            return True
        monkeypatch.setattr(bot, "telegram", dispatch)
        await bot.start()
        task = bot.polling_task
        with pytest.raises(RuntimeError): await bot.start()
        await asyncio.wait_for(reached.wait(), 1)
        assert bot.polling_task is task
        assert bot.offset == 6 and calls[-1]["offset"] == 6
        assert calls[-1]["timeout"] == 30
        assert len(api.answers) == 2
        await bot.stop()
        assert task.cancelled() and bot.polling_task is None


async def test_lifespan_getme_and_owned_client_cleanup():
    requests = []
    blocked = asyncio.Event()
    async def transport(request):
        requests.append(request.url.path.rsplit("/", 1)[1])
        if requests[-1] == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"id": 900, "is_bot": True}})
        await blocked.wait()
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as tg, httpx.AsyncClient() as mcp:
        app = create_app(CONFIG, telegram_client=tg, mcp_client=mcp, telegram_api_url="http://telegram-double")
        async with app.router.lifespan_context(app):
            task = app.state.bot.polling_task
            await asyncio.sleep(0)
            assert app.state.bot.bot_id == 900
        assert task.cancelled()
        assert not tg.is_closed and not mcp.is_closed
    app = create_app(CONFIG)
    bot = app.state.bot
    async def bad_start(): raise TelegramError("failed")
    bot.start = bad_start
    with pytest.raises(TelegramError):
        async with app.router.lifespan_context(app): pass
    assert bot.telegram_client.is_closed and bot.mcp_client.is_closed


@pytest.mark.parametrize("body", [{"ok": False}, {"ok": True, "result": {"id": 900, "is_bot": False}}, {"ok": True, "result": {"id": "900", "is_bot": True}}])
async def test_getme_must_verify_identity(body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        bot = TelegramBot(CONFIG, client, client)
        with pytest.raises(TelegramError): await bot.start()
        assert bot.polling_task is None and bot.bot_id is None


@pytest.mark.parametrize("failure", ["network", "timeout", "invalid_json", "invalid_id", "http"])
async def test_message_delivery_errors_are_safe(failure):
    async def transport(request):
        if failure == "network": raise httpx.ConnectError("telegram-secret", request=request)
        if failure == "timeout": raise TimeoutError("telegram-secret")
        if failure == "invalid_json": return httpx.Response(200, text="not json")
        if failure == "invalid_id": return httpx.Response(200, json={"ok": True, "result": {"message_id": "77"}})
        return httpx.Response(500, text="telegram-secret")
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        bot = TelegramBot(CONFIG, client, client)
        with pytest.raises(TelegramError) as caught:
            await bot.send_message(Message(request_id=RID, type="question", title="t", description="d"))
        assert "secret" not in str(caught.value)


async def test_concurrent_start_cannot_create_two_pollers(setup, monkeypatch):
    api, bot, *_ = setup
    ready = asyncio.Event()
    release = asyncio.Event()
    polling = asyncio.Event()
    async def initialize():
        ready.set()
        await release.wait()
    async def poll():
        await polling.wait()
    monkeypatch.setattr(bot, "initialize", initialize)
    monkeypatch.setattr(bot, "poll_updates", poll)
    first = asyncio.create_task(bot.start())
    await ready.wait()
    second = asyncio.create_task(bot.start())
    release.set()
    await first
    with pytest.raises(RuntimeError): await second
    await bot.stop()


async def test_acceptance_precedes_keyboard_edit(setup):
    api, bot, tg, _ = setup
    forwarding = asyncio.Event()
    allow_acceptance = asyncio.Event()
    async def delayed_mcp(request):
        forwarding.set()
        await allow_acceptance.wait()
        return await api.mcp(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(delayed_mcp)) as mcp:
        bot.mcp_client = mcp
        task = asyncio.create_task(bot.handle_update(callback()))
        await forwarding.wait()
        assert not any(method == "editMessageReplyMarkup" for method, _ in api.calls)
        allow_acceptance.set()
        await task
        assert api.calls[-1][0] == "editMessageReplyMarkup"
