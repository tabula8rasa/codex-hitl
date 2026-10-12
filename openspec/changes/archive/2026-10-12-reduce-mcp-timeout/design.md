# Design

## Context

See `proposal.md` for motivation. The timeout reduction is implemented: `RESPONSE_WAIT_SECONDS = 850` in `src/codex_hitl/mcp_server/lifecycle.py`, and two controlled-time tests independently assert 850. Delivery is bounded separately at 10 seconds; the response timer starts after delivery succeeds. The repository does not contain an MCP client registration: `.codex/config.toml` configures agents only, and the registration examples live in `README.md`. A live call in this chat returned `HITL_TIMEOUT` after 850.38 seconds of wall-clock elapsed time; this verifies the reduced wait, not the proposed Telegram expiry update.

The current lifecycle specification requires 3550 seconds, so the delta intentionally supersedes it. `docs/project.md`, referenced by OpenSpec configuration, is absent; component docs and implementation provide the planning context. The old MVP artifacts are archived, and verification documents contain dated observations and acceptance exceptions.

Before implementing the expiry refinement, MCP validated the delivery response but discarded its `message_id`. Its timeout branch returned immediately without notifying the bot. The bot had no expiry endpoint or pending registry; it sent a separate inactive notification only when a late answer received `accepted: false`. Its message renderer can reconstruct the original text, including the question reply instruction, from the delivered `Message`. The expiry behavior below is now implemented; tests and execution evidence are recorded in `docs/VERIFICATION.md`.

## Goals / Non-Goals

**Goals:** Coordinate the server timing change with client examples, test expectations, current contracts, and operational instructions. Automatically mark the original Telegram message expired, while keeping MCP authoritative for lifecycle decisions and the bot free of pending state. Make remaining old numbers auditable as historical evidence.

**Non-Goals:** Add runtime timeout configuration, change Telegram polling or existing delivery/answer budgets, alter public payloads, edit external user configuration, or reinterpret past test outcomes. Proactive notification for client cancellation, process shutdown/restart, or ambiguous delivery failure is outside this refinement; it covers the server's response-wait timeout.

## Decisions

### Preserve the existing margin

Interpret the requested 3600-to-900 change as the Codex tool budget, because 3600 appears in client examples while the actual server wait is 3550. Use 850 for the response wait to preserve the 50-second client/server difference. Delivery plus response waiting can consume up to 860 seconds, leaving roughly 40 seconds for other overhead within the configured client budget. This is budget arithmetic, not a guarantee about transport scheduling.

Keeping 3550 would make the client expire first. Setting the response wait to 900 would also permit delivery and overhead to exceed the client budget. A new runtime setting would broaden this focused change unnecessarily. A separate 10-second total expiry notification budget increases the planned delivery/wait/notification maximum to 870 seconds, leaving roughly 30 seconds of client budget for other overhead.

### Change the existing constant and tests together

Set the existing constant to 850, retain the module-local timing seam, and change the explicit expectations in `tests/test_mcp_lifecycle.py` and `tests/test_integration_services.py` to 850. Keep explicit numeric assertions so the tests independently enforce the intended contract. Existing tests cover timeout shape, cleanup, late answers, and successful responses; retain those checks. Extend `tests/test_documented_contracts.py` to parse the README TOML example and assert a 900-second HITL budget and sufficient room for the server wait plus delivery. Do not use a shortened production timeout or wait 850 real seconds in automated tests.

### Update current guidance and label historical evidence

Implementation edit inventory:

| File | Treatment |
| --- | --- |
| `README.md` | Update all current 3600/3550 references, both registration paths, timeout constraints, and 59-minute wording to 900/850 and 14 minutes 10 seconds for the response wait. Replace the statement that shortening is only a future decision. |
| `docs/MCP_SERVER.md` | Update algorithm, constraints, current-contract statements, live budget caveat, and controlled-time test description, including hour-long wording; document the expiry call and its failure budget. |
| `docs/IMPLEMENTATION_CONTRACTS.md` | Update current timing contract, internal expiry payload/endpoint, and future live-check guidance. |
| `docs/TELEGRAM_BOT.md` | Document authenticated expiry editing and revise the button-removal rule to allow both acceptance and expiry. |
| `AGENTS.md` | Update the timeout-specific testing instruction so it enforces 850. Other stale repository descriptions are outside this change. |
| `docs/LIVE_SMOKE.md` | Update the current procedure to 900/850; require automatic original-message editing and button removal without a click. Label old observations and acceptance notes as the previous 3600/3550 contract. The recorded 961.926-second approval remains historical and is not acceptance evidence for the new budget. |
| `docs/TEST_REPORT.md`, `docs/VERIFICATION.md` | Label prior reports as historical, preserve measurements and prior PASS/exception decisions, and add current automated results only after execution. Revise any active follow-up instructions to the new budget. |
| `openspec/specs/` | Sync all three delta specs during an explicit sync/archive workflow; until then the active change declares the intended replacement contract. |

Archived artifacts under `openspec/changes/archive/2026-10-11-implement-hitl-mvp/` retain their original values. A blind global replacement would falsify history. No timeout-dependent values were found in `skills/hitl/SKILL.md`, `docs/SKILL.md`, `.env.example`, Compose, Dockerfile, or repository-local Codex configuration that require this change. Delivery (10), Telegram polling (30/40), and test harness timeouts are independent and remain intact. Telegram documentation does require the expiry behavior update listed above.

### Notify expiry without a bot-side registry

Retain the successfully returned Telegram `message_id` in the running MCP request coroutine alongside the original `Message`. Add a strict shared `ExpiryNotification` model with exactly `message_id` (positive integer) and `message` (the existing `Message` model with canonical request UUID). Send it to `POST /internal/expire` on the bot's configured base URL with the existing internal Bearer authentication. The bot selects only its configured Telegram chat; callers cannot supply another chat or token. Return HTTP 200 with `{"updated":true}` on confirmed success; reject malformed/unauthorized requests before Telegram effects and return a safe HTTP 502 on Telegram edit failure.

This carries the metadata needed to identify and reconstruct the original message without a bot-side registry, a database, or a new public tool field. A bot-side timer/map would duplicate MCP authority and introduce restart/state coordination. Polling Telegram for message text is unnecessary because the existing renderer deterministically constructs it from the original request.

### Expire before awaiting external work

Only the response wait's timeout branch sends an expiry notification. Remove the exact pending entry and ensure its Future is terminal before the first notification await; preserve the existing final cleanup as an idempotent safeguard. Thus a callback racing with message editing receives `accepted: false`. An answer that completes the wait returns normally and never schedules expiry editing.

Wrap the complete outgoing expiry call, including response validation, in a new 10-second total async boundary, with an HTTP timeout as well. The bot awaits its edit inside the existing bounded Telegram operation. No untracked background task, automatic notification retry, or persistent recovery is introduced. A bot/network/Telegram error is logged safely; the original call still returns `{"status":"timeout","error_code":"HITL_TIMEOUT"}` and cannot reopen. Application cancellation still propagates normally rather than being swallowed as an ordinary notification failure.

### Edit the original message in one operation

Use the existing renderer to reconstruct the exact request text and append two newlines followed by `This request is no longer active. Your answer was not accepted.`. Send one `editMessageText` operation with the original message ID, configured chat ID, full resulting text, and `reply_markup: {"inline_keyboard": []}`. This combines text editing and control removal without a partially completed two-operation success path. Do not send a separate expiry message. Questions retain their original direct-reply instruction and receive the same final notice even though they had no buttons.

Repeated identical notifications reconstruct the same text, so the suffix does not accumulate. Treat an already-applied identical edit as success; do not treat arbitrary Telegram errors as successful updates. If editing is impossible (deleted message, text too long, permissions, or API failure), surface a safe failure rather than truncating the original text or claiming success. MCP still expires the request. The existing inactive-answer notification remains a fallback for late replies/callbacks, including those occurring during editing or after an editing failure.

### Verify expiry effects and regressions

Extend shared-model/auth tests and the Telegram HTTP double to exercise `editMessageText` with text plus an empty keyboard. Controlled-time lifecycle and integrated SDK tests must assert the timeout result, request inactivity before notification finishes, correct message correlation across concurrent requests, expiry edits for all request types, and no expiry edit after an accepted answer. Cover duplicate notification, missing/wrong credentials, malformed payload, Telegram edit failure, bot unavailability, total notification timeout, and late answers during notification. Update the parsed client-budget check to include the new expiry budget. Keep the production response wait at 850 seconds; any Docker timeout scenario must use a test-only controlled-time seam and rebuild images before claiming E2E success.

### Audit completeness explicitly

After applying, search tracked and hidden project files for `3600`, `3550`, underscore variants, `tool_timeout_sec`, `RESPONSE_WAIT_SECONDS`, and hour/59-minute wording. Classify remaining old values as archived history, explicitly labeled historical observations, or old-to-new migration explanation. No active instruction, runtime wait, or assertion may retain the old budget. This semantic audit complements the automated tests without asserting that all historical numbers must disappear.

## Risks / Trade-offs

- Users now have 14 minutes 10 seconds to respond after delivery → document the behavior change prominently.
- A locally registered client still uses its old setting → provide the exact `tool_timeout_sec = 900` migration instruction; repository apply does not edit external configuration.
- Old wording could look current → label historical report sections and update live follow-up instructions, while preserving original evidence.
- Expiry editing consumes part of the remaining client margin → enforce a 10-second total notification boundary and retain the timeout result on failure.
- Telegram editing can fail or race with a user's click → keep MCP inactive before notification, log safe failures, and retain inactive-answer feedback; message appearance is not lifecycle authority.
- Automated tests cannot prove live Telegram expiry editing → keep the current live procedure and record new results only if actually executed. The observed 850.38-second call verifies the timing behavior only; the prior 961.926-second approval is not proof of this contract.

## Migration Plan

Apply the remaining runtime, tests, and documentation as one coordinated change; run focused tests, the ordinary non-Docker suite, and rebuilt-image Docker E2E. Deploy the bot's expiry endpoint before MCP begins using it, or rebuild/restart both together when no requests are pending. The client entry remains 900. Sync all three specs through the normal explicit workflow; do not auto-archive. If a live check is executed, record actual timing and verify message editing without clicking, independently of automated verification.

Rolling back only the expiry refinement leaves the implemented 850/900-second timing contract in place; roll back MCP's notification sender before removing the bot endpoint. Rolling back the entire timeout change restores the former code/guidance and external client entry to 3600. Restarting MCP loses pending requests under the existing RAM-only contract, so perform deployment when no requests are pending. Previously edited Telegram messages are not restored by rollback.
