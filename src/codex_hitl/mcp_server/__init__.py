"""SDK MCP transport and authenticated internal answer application."""
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from codex_hitl.auth import require_internal_token
from codex_hitl.config import MCPConfig
from codex_hitl.contracts import Acceptance, AnswerRequest, Request
from codex_hitl.mcp_server.lifecycle import RequestService


def create_app(config: MCPConfig | None = None, *, bot_client: httpx.AsyncClient | None = None) -> FastAPI:
    config = config or MCPConfig.from_env()
    client = bot_client or httpx.AsyncClient()
    service = RequestService(config, client)
    server = Server("codex-hitl")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(
            name="hitl.request",
            description="Wait for a user decision, direct text answer, or manual action through Telegram.",
            inputSchema=Request.model_json_schema(),
        )]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> dict:
        if name != "hitl.request":
            raise ValueError("Unknown tool")
        return await service.request(Request.model_validate(arguments))

    # The documented MCP listener is loopback-only. Explicit SDK settings are
    # required: the session manager otherwise disables rebinding protection.
    loopback_hosts = ["localhost", "127.0.0.1", "[::1]"]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[value for host in loopback_hosts for value in (host, host + ":*")],
        allowed_origins=[value for host in loopback_hosts
                         for value in ("http://" + host, "http://" + host + ":*")],
    )
    manager = StreamableHTTPSessionManager(
        server, stateless=True, json_response=True, security_settings=security,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            async with manager.run():
                yield
        finally:
            service.shutdown()
            if bot_client is None:
                await client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.state.service = service
    app.state.mcp_server = server

    @app.post("/internal/answer", response_model=Acceptance,
              dependencies=[Depends(require_internal_token(config.internal_api_token))])
    async def receive_answer(answer: AnswerRequest) -> Acceptance:
        return Acceptance(accepted=service.receive_answer(answer))

    # ASGI endpoint object, not a request callable: SDK owns HTTP/JSON-RPC.
    class MCPTransport:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    app.router.routes.append(Route("/mcp", endpoint=MCPTransport()))
    return app
