# Proposal

## Why

Codex and its subagents need a way to obtain a blocking user decision through Telegram and resume the original tool call. The repository records an agreed MVP contract but contains no application code, tests, or deployment configuration.

## What Changes

- Deliver the `hitl` agent skill with the invocation and failure behavior documented in `docs/SKILL.md`.
- Implement `hitl.request(type, title, description)` and the in-memory request lifecycle, including concurrent requests, first-valid-response acceptance, cleanup, and the fixed 3550-second timeout.
- Implement Telegram message delivery and long polling for approvals, direct text answers, and manual-action confirmations, with authorized-user checks and post-acceptance button removal.
- Protect internal HTTP interfaces with a shared token and package MCP and bot services as two Docker containers launched by Compose.
- Add automated contract, lifecycle, bot, and integration tests and document setup and a live Codex/Telegram smoke test.
- Keep persistence, delivery recovery, a cancellation API, identity propagation, and timeout changes outside this MVP.

## Capabilities

### New Capabilities

- `hitl-agent-interaction`: When agents request user involvement and how they handle decisions, timeout, and tool unavailability.
- `hitl-request-lifecycle`: The MCP tool contract, concurrent pending requests, response validation, and terminal cleanup.
- `telegram-hitl-interaction`: Telegram rendering, authorized response correlation, response forwarding, and message updates.
- `hitl-deployment`: Two-service deployment, required configuration, and internal API authentication.

### Modified Capabilities

None; the OpenSpec capability inventory is empty.

## Impact

Introduces Python application packages for MCP and Telegram, dependencies on the MCP Python SDK and FastAPI, HTTP integration with the Telegram Bot API, Docker/Compose files, tests, and an installable `hitl` skill. Adds `POST /mcp`, `POST /internal/messages`, and `POST /internal/answer`; no existing implemented API is changed. Requirements come from `README.md`, `docs/SKILL.md`, `docs/MCP_SERVER.md`, and `docs/TELEGRAM_BOT.md`; the configured `docs/project.md` does not exist.
