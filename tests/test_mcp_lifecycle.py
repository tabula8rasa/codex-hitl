import asyncio
from uuid import UUID, uuid4

import httpx
import pytest

from codex_hitl.config import MCPConfig
from codex_hitl.contracts import AnswerRequest, Request
from codex_hitl.mcp_server import create_app
from codex_hitl.mcp_server import lifecycle
from codex_hitl.mcp_server.lifecycle import DeliveryError, RequestService

CONFIG = MCPConfig("component-token", "http://bot")


def answer(request_id, status="approved", **kwargs):
    return AnswerRequest(request_id=request_id, answer={"status": status, **kwargs})


def setup_service(handler=None):
    messages = asyncio.Queue()

    async def deliver(request):
        import json
        message = json.loads(request.content)
        await messages.put(message)
        if handler:
            return await handler(message)
        return httpx.Response(200, json={"message_id": 1})

    client = httpx.AsyncClient(transport=httpx.MockTransport(deliver))
    return RequestService(CONFIG, client), messages, client


@pytest.mark.parametrize("kind,status,text", [
    ("approval", "approved", None), ("approval", "rejected", None),
    ("question", "answered", "a direct answer"),
    ("manual_action", "completed", None), ("manual_action", "unable", None),
])
async def test_all_results(kind, status, text):
    service, messages, client = setup_service()
    async with client:
        task = asyncio.create_task(service.request(Request(type=kind, title="", description="")))
        message = await messages.get()
        assert UUID(message["request_id"]).version == 4
        result = answer(message["request_id"], status, **({"answer": text} if text else {}))
        assert service.receive_answer(result)
        assert await task == result.answer.model_dump()
        assert not service.pending


async def test_concurrency_out_of_order_and_competing_answers():
    service, messages, client = setup_service()
    async with client:
        first = asyncio.create_task(service.request(Request(type="approval", title="first", description="")))
        one = await messages.get()
        second = asyncio.create_task(service.request(Request(type="approval", title="second", description="")))
        two = await messages.get()
        assert not service.receive_answer(answer(one["request_id"], "answered", answer="wrong"))
        assert not service.receive_answer(answer(str(uuid4())))
        assert service.receive_answer(answer(two["request_id"], "rejected"))
        assert not service.receive_answer(answer(two["request_id"]))
        assert await second == {"status": "rejected"}
        assert not first.done()
        assert service.receive_answer(answer(one["request_id"]))
        assert await first == {"status": "approved"}
        assert not service.receive_answer(answer(one["request_id"]))
        assert not service.pending


async def test_early_answer_during_delivery():
    async def handler(message):
        assert message["request_id"] in service.pending
        assert service.receive_answer(answer(message["request_id"]))
        await asyncio.sleep(0)
        return httpx.Response(200, json={"message_id": 1})

    service, _, client = setup_service(handler)
    async with client:
        assert await service.request(Request(type="approval", title="", description="")) == {"status": "approved"}
        assert not service.pending


async def test_fixed_timeout_cleanup_and_late_answer(monkeypatch):
    waits = []

    async def expire(future, seconds):
        waits.append(seconds)
        future.cancel()
        raise TimeoutError

    monkeypatch.setattr(lifecycle, "wait_for", expire)
    service, messages, client = setup_service()
    async with client:
        assert await service.request(Request(type="question", title="", description="")) == {
            "status": "timeout", "error_code": "HITL_TIMEOUT"}
        message = await messages.get()
        assert waits == [3550]
        assert not service.receive_answer(answer(message["request_id"], "answered", answer="late"))
        assert not service.pending


@pytest.mark.parametrize("failure", ["http", "network", "timeout", "bad_body"])
async def test_delivery_error_cleanup(failure):
    async def fail(message):
        if failure == "network":
            raise httpx.ConnectError("sensitive detail")
        if failure == "timeout":
            raise TimeoutError("sensitive detail")
        return httpx.Response(500 if failure == "http" else 200, json={"unexpected": True})

    service, messages, client = setup_service(fail)
    async with client:
        with pytest.raises(DeliveryError, match="HITL message delivery failed") as exc:
            await service.request(Request(type="approval", title="", description=""))
        assert "sensitive" not in str(exc.value)
        message = await messages.get()
        assert not service.pending
        assert not service.receive_answer(answer(message["request_id"]))


@pytest.mark.parametrize("during_delivery", [False, True])
async def test_cancellation_cleanup_and_new_instance(during_delivery):
    gate = asyncio.Event()

    async def block(message):
        if during_delivery:
            await gate.wait()
        return httpx.Response(200, json={"message_id": 1})

    service, messages, client = setup_service(block)
    async with client:
        task = asyncio.create_task(service.request(Request(type="approval", title="", description="")))
        message = await messages.get()
        entry = service.pending[message["request_id"]]
        new_service = RequestService(CONFIG, client)
        assert not new_service.receive_answer(answer(message["request_id"]))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert entry.future.cancelled()
        assert not service.pending
        assert not service.receive_answer(answer(message["request_id"]))


async def test_already_cancelled_future_rejected():
    service, messages, client = setup_service()
    async with client:
        task = asyncio.create_task(service.request(Request(type="approval", title="", description="")))
        message = await messages.get()
        service.pending[message["request_id"]].future.cancel()
        assert not service.receive_answer(answer(message["request_id"]))
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service.pending


async def test_internal_http_auth_validation_and_first_acceptance():
    service, messages, bot_client = setup_service()
    app = create_app(CONFIG, bot_client=bot_client)
    service = app.state.service
    async with bot_client, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as http:
        task = asyncio.create_task(service.request(Request(type="approval", title="", description="")))
        message = await messages.get()
        payload = answer(message["request_id"]).model_dump()
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            response = await http.post("/internal/answer", json=payload, headers=headers)
            assert response.status_code == 401
            assert not task.done()
        headers = {"Authorization": "Bearer component-token"}
        malformed = await http.post("/internal/answer", json={"request_id": message["request_id"], "answer": {"status": "answered"}}, headers=headers)
        assert malformed.status_code == 422
        assert not task.done()
        responses = await asyncio.gather(*[http.post("/internal/answer", json=payload, headers=headers) for _ in range(2)])
        assert sorted(r.json()["accepted"] for r in responses) == [False, True]
        assert await task == {"status": "approved"}
        assert not service.pending


async def test_total_delivery_budget_is_ten_seconds(monkeypatch):
    from contextlib import asynccontextmanager

    budgets = []

    @asynccontextmanager
    async def expired_budget(seconds):
        budgets.append(seconds)
        yield
        raise TimeoutError

    monkeypatch.setattr(lifecycle, "timeout", expired_budget)
    service, messages, client = setup_service()
    async with client:
        with pytest.raises(DeliveryError):
            await service.request(Request(type="approval", title="", description=""))
        message = await messages.get()
        assert budgets == [10]
        assert not service.pending
        assert not service.receive_answer(answer(message["request_id"]))


async def test_shutdown_cancels_waiters():
    service, messages, client = setup_service()
    async with client:
        task = asyncio.create_task(service.request(Request(type="approval", title="", description="")))
        message = await messages.get()
        service.shutdown()
        assert not service.pending
        assert not service.receive_answer(answer(message["request_id"]))
        with pytest.raises(asyncio.CancelledError):
            await task
