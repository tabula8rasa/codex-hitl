import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from codex_hitl.config import MCPConfig
from codex_hitl.contracts import AnswerRequest
from codex_hitl.mcp_server import create_app


@asynccontextmanager
async def sdk_session(app):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            async with streamable_http_client("http://127.0.0.1:8100/mcp", http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session


async def test_sdk_discovers_exact_tool_and_validates_before_effects():
    sent = []

    async def deliver(request):
        sent.append(request)
        return httpx.Response(200, json={"message_id": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(deliver)) as bot:
        app = create_app(MCPConfig("test", "http://bot"), bot_client=bot)
        async with sdk_session(app) as session:
            listing = await session.list_tools()
            assert [t.name for t in listing.tools] == ["hitl.request"]
            schema = listing.tools[0].inputSchema
            assert set(schema["properties"]) == {"type", "title", "description"}
            assert set(schema["required"]) == {"type", "title", "description"}
            assert schema["additionalProperties"] is False
            for arguments in (
                {"type": "invalid", "title": "", "description": ""},
                {"type": "approval", "title": ""},
                {"type": "approval", "title": "", "description": "", "agent_name": "no"},
                {"type": "approval", "title": 1, "description": ""},
            ):
                result = await session.call_tool("hitl.request", arguments)
                assert result.isError
                assert not sent
                assert not app.state.service.pending


async def test_sdk_returns_original_call_result_and_delivery_errors():
    import json

    async def deliver(request):
        message = json.loads(request.content)
        if message["title"] == "failure":
            return httpx.Response(503)
        assert app.state.service.receive_answer(AnswerRequest(
            request_id=message["request_id"], answer={"status": "answered", "answer": "from SDK"}))
        return httpx.Response(200, json={"message_id": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(deliver)) as bot:
        app = create_app(MCPConfig("test", "http://bot"), bot_client=bot)
        async with sdk_session(app) as session:
            result = await session.call_tool("hitl.request", {"type": "question", "title": "", "description": ""})
            assert not result.isError
            assert result.structuredContent == {"status": "answered", "answer": "from SDK"}
            failed = await session.call_tool("hitl.request", {"type": "question", "title": "failure", "description": ""})
            assert failed.isError
            assert not app.state.service.pending


@pytest.mark.parametrize("host,origin,status", [
    ("attacker.invalid:8100", "http://attacker.invalid:8100", 421),
    ("attacker.invalid:8100", None, 421),
    ("127.0.0.1:8100", "http://attacker.invalid:8100", 403),
    ("127.0.0.1.attacker.invalid:8100", "http://127.0.0.1:8100", 421),
    ("127.0.0.1:8100", "http://127.0.0.1.attacker.invalid:8100", 403),
])
async def test_dns_rebinding_rejected_before_delivery(host, origin, status):
    sent = []

    async def deliver(request):
        sent.append(request)
        return httpx.Response(200, json={"message_id": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(deliver)) as bot:
        app = create_app(MCPConfig("test", "http://bot"), bot_client=bot)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                headers = {"Host": host, "Accept": "application/json, text/event-stream"}
                if origin:
                    headers["Origin"] = origin
                response = await client.post("http://127.0.0.1:8100/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "hitl.request", "arguments": {
                        "type": "approval", "title": "attack", "description": "attack"}},
                })
                assert response.status_code == status
                assert not sent
                assert not app.state.service.pending


@pytest.mark.parametrize("host,origin", [
    ("127.0.0.1:8100", "http://127.0.0.1:8100"),
    ("localhost:8100", "http://localhost:8100"),
    ("[::1]:8100", "http://[::1]:8100"),
])
async def test_loopback_host_and_origin_allowed(host, origin):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as bot:
        app = create_app(MCPConfig("test", "http://bot"), bot_client=bot)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                response = await client.post("http://127.0.0.1:8100/mcp", headers={
                    "Host": host, "Origin": origin,
                    "Accept": "application/json, text/event-stream",
                }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
                assert response.status_code == 200
                assert response.json()["result"]["tools"][0]["name"] == "hitl.request"
