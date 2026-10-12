"""QA-only controlled expiry trigger; never packaged in a production image."""
import asyncio
from contextlib import suppress

from fastapi import Depends

from codex_hitl.auth import require_internal_token
from codex_hitl.config import MCPConfig
from codex_hitl.mcp_server import create_app, lifecycle


def factory():
    config = MCPConfig.from_env()
    app = create_app(config)
    expire = asyncio.Event()

    async def controlled_wait(future, seconds):
        assert seconds == 850
        trigger = asyncio.create_task(expire.wait())
        try:
            done, _ = await asyncio.wait({future, trigger}, timeout=seconds,
                                         return_when=asyncio.FIRST_COMPLETED)
            if future in done:
                return future.result()
            future.cancel()
            raise TimeoutError
        finally:
            trigger.cancel()
            with suppress(asyncio.CancelledError):
                await trigger

    lifecycle.wait_for = controlled_wait

    @app.post('/qa/expire', dependencies=[Depends(require_internal_token(config.internal_api_token))])
    async def trigger_expiry():
        expire.set()
        return {'triggered': True}

    return app
