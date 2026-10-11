"""FastAPI message endpoint with one managed Telegram poller."""
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException

from codex_hitl.auth import require_internal_token
from codex_hitl.config import BotConfig
from codex_hitl.contracts import Message, MessageResponse
from .service import TelegramBot, TelegramError


def create_app(config: BotConfig | None = None, *, telegram_client: httpx.AsyncClient | None = None, mcp_client: httpx.AsyncClient | None = None, telegram_api_url: str = "https://api.telegram.org") -> FastAPI:
    config = config or BotConfig.from_env()
    owned_telegram = telegram_client is None
    owned_mcp = mcp_client is None
    telegram_client = telegram_client or httpx.AsyncClient()
    mcp_client = mcp_client or httpx.AsyncClient()
    bot = TelegramBot(config, telegram_client, mcp_client, telegram_api_url=telegram_api_url)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await bot.start()
            yield
        finally:
            await bot.stop()
            if owned_telegram:
                await telegram_client.aclose()
            if owned_mcp:
                await mcp_client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.state.bot = bot

    @app.post("/internal/messages", response_model=MessageResponse, dependencies=[Depends(require_internal_token(config.internal_api_token))])
    async def messages(message: Message):
        try:
            return MessageResponse(message_id=await bot.send_message(message))
        except TelegramError:
            raise HTTPException(status_code=502, detail="Telegram message delivery failed") from None

    return app
