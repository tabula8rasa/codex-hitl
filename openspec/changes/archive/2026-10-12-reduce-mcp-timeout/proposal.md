# Proposal

## Why

This change reduces the former 3600-second Codex tool budget and 3550-second response wait to 900/850 seconds. Expired Telegram messages must also visibly become inactive without waiting for the user to click a stale button.

## What Changes

- **BREAKING**: Reduce the configured Codex tool budget from 3600 to 900 seconds and the fixed server response wait from 3550 to 850 seconds, preserving the existing 50-second margin and separate 10-second delivery budget.
- Update controlled-time assertions, current documentation, client configuration examples, repository guidance, and the live timeout procedure together.
- Clearly distinguish historical verification records using the former budget from current instructions; retain their original measurements and acceptance exceptions.
- Keep the tool schema, timeout result, cleanup, and late-answer rejection behavior intact.
- On server timeout, notify the Telegram bot through an authenticated internal call. The bot edits the original message, removes its buttons, and appends exactly `This request is no longer active. Your answer was not accepted.` for approval, manual-action, and question requests.
- Bound expiry notification work and retain `HITL_TIMEOUT` and terminal cleanup if notification or Telegram editing fails.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `hitl-request-lifecycle`: Enforce an 850-second response wait after successful delivery and notify the bot when that wait expires.
- `hitl-deployment`: Document a 900-second Codex tool budget for the supplied deployment.
- `telegram-hitl-interaction`: Automatically mark the original message inactive and remove buttons on authenticated expiry notification.

## Impact

- Runtime: `src/codex_hitl/mcp_server/lifecycle.py`, `src/codex_hitl/contracts.py`, and the Telegram bot app/service. Add an internal expiry payload and endpoint; the public tool payload is unchanged.
- Tests: MCP lifecycle, shared contracts, Telegram component, SDK integration, and client-budget documentation checks; extend the Docker test double/E2E for message edits.
- Current guidance: `README.md`, `docs/MCP_SERVER.md`, `docs/TELEGRAM_BOT.md`, `docs/IMPLEMENTATION_CONTRACTS.md`, `docs/LIVE_SMOKE.md`, and `AGENTS.md` where applicable.
- Verification context: `docs/TEST_REPORT.md` and `docs/VERIFICATION.md` need a clear historical/current boundary without rewriting prior outcomes. Archived OpenSpec artifacts retain the former contract as history.
- No dependency, Telegram polling, Compose service, credential, or public payload changes. MCP retains message metadata only for the duration of the request; the bot gains no pending-state registry. Existing external Codex registrations require the operator to update `tool_timeout_sec`; applying this repository change does not modify user-global configuration.
