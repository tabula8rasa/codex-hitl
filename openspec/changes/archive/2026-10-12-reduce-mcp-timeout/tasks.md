# Tasks

## 1. Response wait and current server contract

- [x] 1.1 Change `RESPONSE_WAIT_SECONDS` in `src/codex_hitl/mcp_server/lifecycle.py` to 850 and update the explicit timing assertions in `tests/test_mcp_lifecycle.py` and `tests/test_integration_services.py`; verify `python -m pytest tests/test_mcp_lifecycle.py tests/test_integration_services.py -q` passes with timeout shape, cleanup, late-answer rejection, and the unchanged 10-second delivery boundary covered.
- [x] 1.2 Align the current timing contract in `docs/MCP_SERVER.md`, `docs/IMPLEMENTATION_CONTRACTS.md`, and the timeout testing guidance in `AGENTS.md` with 850 seconds for response waiting and 900 seconds for the client; verify the described sequence still starts the response timer after delivery and has no runtime response override or conflicting future-only shortening statement.

## 2. Client registration and operational instructions

- [x] 2.1 Update all current timeout statements and both client registration paths in `README.md` to 900/850, including human-readable durations; add a parsed TOML registration check in `tests/test_documented_contracts.py` asserting the 900-second client budget and room for the 850-second wait plus 10-second delivery; verify `python -m pytest tests/test_documented_contracts.py -q` passes and both registration instructions specify 900.
- [x] 2.2 Update the active procedure in `docs/LIVE_SMOKE.md` to measure an unanswered 850-second wait returning `HITL_TIMEOUT` before 900 seconds and reject a late answer; clearly label retained observations as historical evidence from the former contract, and verify the 961.926-second approval is not presented as validation of the new budget.
- [x] 2.3 Add historical/current context to `docs/TEST_REPORT.md` and `docs/VERIFICATION.md`, revise active follow-up instructions to 900/850, and preserve original elapsed measurements and acceptance exceptions; verify no former live result is rewritten or claimed as a new timeout PASS.

## 3. Integrated verification and completeness audit

- [x] 3.1 Run `python -m pytest tests --ignore=tests/test_e2e_docker.py -q` and `openspec validate reduce-mcp-timeout --strict`; record actual commands/results in the verification documentation and leave live elapsed-time verification explicitly unverified unless separately executed.
- [x] 3.2 Audit hidden and tracked project files with `rg -n --hidden -g '!.git' -g '!.env' '3600|3550|3_600|3_550|tool_timeout_sec|RESPONSE_WAIT_SECONDS|59 minutes|hour' .`; verify each remaining old value is archived history, labeled historical evidence, an explicit migration explanation, or the pending main-spec sync, and no active code, assertion, or operator instruction retains the former budget. Record the reviewed exceptions.

## 4. Authenticated bot expiry editing

- [x] 4.1 Add the strict shared `ExpiryNotification` payload (`message_id`, existing `Message`) and authenticated `POST /internal/expire` endpoint; document payload, `{"updated":true}` success, and safe failure responses in `docs/IMPLEMENTATION_CONTRACTS.md` and `docs/TELEGRAM_BOT.md`. Verify shared-model and bot endpoint tests reject extra/invalid fields and missing/wrong credentials before Telegram effects and use only the configured chat.
- [x] 4.2 Implement original-message expiry editing using the existing renderer and one text edit with an empty inline keyboard, preserving original text and appending the exact notice once for all three request types. Update the Telegram acceptance-versus-expiry documentation and verify component tests cover approval/manual/question messages, repeated identical notifications, already-applied edits, and deleted/oversized/permission/API failures without truncation or false success.

## 5. MCP expiry notification and coordinated verification

- [x] 5.1 Retain delivered message metadata in the MCP request coroutine, make timed-out requests inactive before notifying the bot, and bound the full authenticated expiry call at 10 seconds while retaining timeout result and cleanup on failure. Document the new flow in `docs/MCP_SERVER.md` and verify lifecycle tests cover success, bot/network/Telegram failure, total notification timeout, cancellation propagation, late answers during notification, and no expiry notification after an accepted answer.
- [x] 5.2 Extend the integrated SDK/Telegram double tests for automatic expiry updates across all request types and concurrent-message correlation, and update the documented client-budget test to include delivery, response wait, and expiry notification budgets. Verify focused contract, lifecycle, bot, documented-contract, and service integration tests pass with the fixed 850-second production wait and unchanged public tool schema/result shapes.
- [x] 5.3 Update README and the current live-smoke procedure to require automatic button removal and the exact final notice on the original message before user interaction, including failure limitations. Verify the procedure distinguishes the earlier 850.38-second timing observation from the still-unverified live expiry-edit behavior, and keeps historical records intact.
- [x] 5.4 Extend the Docker Telegram double/E2E to verify expiry text and keyboard effects through both services using controlled timing only in a test adapter; rebuild both images and run the enabled E2E and non-Docker suite. Run strict OpenSpec validation and diff checks, recording actual results in verification reports without claiming live execution or weakening existing checks.

## Workflow follow-up

- Sync all three delta specs with the explicit OpenSpec sync workflow before finalizing the change; confirm the main lifecycle spec specifies 850, deployment specifies a 900-second client budget, and Telegram behavior includes automatic expiry editing.
- After deployment, update the external Codex HITL registration to `tool_timeout_sec = 900` and rebuild/restart MCP when no requests are pending. These are operator actions, not repository-local configuration edits.
- If requested and live access is available, execute the revised unanswered-call procedure and record actual timing, result, automatic message editing before any click, and late-answer behavior. The prior 850.38-second timeout verifies timing only, and the earlier 961.926-second approval is not proof of the new behavior.
- Do not archive automatically.

## Archive acceptance — 2026-10-12

All three delta specs were synced and verified against the main specs. Three parallel unanswered live calls returned `HITL_TIMEOUT` after 850.777, 850.711, and 850.693 seconds; the operator confirmed automatic Telegram updates and requested archive, commits, and push. See `docs/LIVE_SMOKE.md` for the detailed live evidence.
