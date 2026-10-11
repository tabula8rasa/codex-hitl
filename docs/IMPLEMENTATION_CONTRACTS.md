# Implementation contracts and ownership

Approved change: `implement-hitl-mvp`. Read its proposal, design, all four capability specs, and tasks before implementation. The configured `docs/project.md` is absent; README and component docs supply the contract.

## Exclusive ownership

- Master: project packaging, `src/codex_hitl/{__init__,contracts,config,auth}.py`, shared/config/skill/deployment tests, Docker/Compose, README, skill, this document, verification report, design implementation notes, and OpenSpec tasks.
- MCP developer: `src/codex_hitl/mcp_server/`, `tests/test_mcp*.py`, `docs/MCP_SERVER.md`.
- Telegram developer: `src/codex_hitl/telegram_bot/`, `tests/test_telegram*.py`, `docs/TELEGRAM_BOT.md`.
- Tester (after integration): `tests/test_integration*.py`, `tests/test_e2e*.py`, `tests/support/`, `docs/TEST_REPORT.md`; no production edits.
- Strict reviewer: read only; no edits.

Developers are concurrent and must accommodate shared workspace edits without reverting others. Only Master updates tasks.md. No commits or archive are requested.

## Shared API

`contracts.py` defines strict extra-forbidding models: `Request(type,title,description)`, `Message(Request + request_id)`, `AnswerRequest(request_id,answer)`, `Decision(status)`, `TextAnswer(status='answered',answer=str)`, `TimeoutResult`, `MessageResponse(message_id=int)`, `Acceptance(accepted=bool)`. IDs are canonical UUIDv4 strings. `answer_matches(type, answer)` validates compatibility. Public schema has exactly three required fields. Internal answers are nested result objects.

Both internal POST routes require `Authorization: Bearer <INTERNAL_API_TOKEN>`. Use `require_internal_token(token)` as a FastAPI dependency; `internal_headers(token)` supplies outgoing headers. Reject authorization before effects. `MCPConfig(internal_api_token,bot_api_url)` and `BotConfig(internal_api_token,telegram_bot_token,telegram_chat_id,telegram_allowed_user_id,hitl_api_url)` expose `from_env()` loaders. Service URLs are base URLs; append `/internal/messages` or `/internal/answer`.

Factories: `codex_hitl.mcp_server.create_app(config=None, ...)`, `codex_hitl.telegram_bot.create_app(config=None, ...)`. Optional injected clients/test adapters may be chosen by each owner, documented for QA. CLI via `uvicorn codex_hitl.mcp_server:create_app --factory --host 0.0.0.0 --port 8100 --workers 1` and corresponding `telegram_bot` on 8101. SDK version is pinned to MCP 1.30.0; inspect installed APIs. Fixed response wait 3550 seconds; total bot delivery boundary 10 seconds. No runtime response timeout override.

Bot correlation first line: `HITL <canonical-uuidv4> <approval|question|manual_action>`. Callback data: `approve:<uuid>`, `reject:<uuid>`, `done:<uuid>`, `unable:<uuid>`. Validate callback action against original message marker, original sender is this bot (getMe identity), and configured chat. Text only through direct replies to bot-authored marked messages. No bot pending registry, invented identity, or delivery retry.

## Dependencies and phase gates

Shared models/config/auth and packaging precede developers. Both developers finish and pass their component tests before Master integrates. Tester starts only after integration; reviewer only after successful automated testing. Defects go to their owners, followed by tests and independent re-review. Docker build/start checks use test doubles and no real credentials. Real Codex/Telegram smoke and unchanged 3550-second live budget require operator credentials/client access and must remain incomplete if unavailable.
