# Operator Codex/Telegram smoke procedure

Requires a Telegram bot token, configured chat and allowed user, local shared token, Docker, and an actual Codex client connected as described in README. Do not place secrets in reports. Do not run another poller for the same bot. Use a dedicated test bot/chat.

1. Build/start Compose and install/register the skill and MCP server. Record client version, SDK version, date, and configuration without secrets.
2. Discover tools in Codex: exactly `hitl.request`, with required `type`, `title`, `description` and no other inputs.
3. Request approval. Click Approve, check the original call returns `approved` and buttons disappear. Repeat with Reject; confirm the agent does not perform the rejected action.
4. Request a question. Ordinary text must not resolve it. Reply directly to the bot message with text; check the original call returns `answered` and the exact answer.
5. Request a manual action. Text replies must be deleted without resolving the call. Done returns `completed`; a separate Unable request returns `unable` and the agent does not assume success.
6. If the client supports subagents, issue root and subagent requests concurrently. Answer them in reverse order and verify each original call receives its own result. Record unsupported client behavior explicitly.
7. Attempt a duplicate/old response and a response from an unauthorized user. Neither may complete another call. Observe inactive notification for a valid duplicate.
8. For the long-running budget, configure `tool_timeout_sec=3600`, issue a request and leave it unanswered. Record monotonic start/end times and original result. Verify the production wait remains 3550, the call returns `{"status":"timeout","error_code":"HITL_TIMEOUT"}` before 3600 seconds, and a late reply is inactive. Do not simulate time or reduce the timeout for this check.
9. Record disconnect behavior separately: cancel a waiting client call and record whether cancellation reaches the server immediately or the fixed timeout bounds cleanup. Restart MCP and verify old answers are inactive.
10. Stop Compose. Record each observed outcome, elapsed time, any transport/proxy/client timeout, and failures. Leave tasks 6.3/6.4 incomplete when access or observations are missing.

## Execution status

The original implementation session had no live connection. A subsequent live acceptance session on 2026-10-11 used the configured Codex MCP tool and real Telegram responses. Automated test-double results remain separate.

### Live acceptance session, 2026-10-11

- Operator reports the basic approval, question, manual-action connection and forbidden-text deletion checks already passed. These earlier checks were not independently observed in this session.
- Four concurrent root calls returned their expected statuses: A1 `approved` (11.838 s), A2 `rejected` (16.293 s), M1 `completed` (18.241 s), M2 `unable` (20.793 s). Rejection was not treated as authorization; inability was not treated as completion. No external action was performed.
- Two concurrent question subagents: Q2 received `{"status":"answered","answer":"BRAVO"}` after 34.141 s; Q1 subsequently received `{"status":"answered","answer":"THIS"}` after 47.326 s. Q1 was still pending when Q2 returned. The actual Q1 text differed from the suggested `ALPHA`; the received text is recorded verbatim. Distinct answers returned to their respective original calls.
- Two concurrent mixed-type subagents: manual-action MIX2 returned `unable` after 18.326 s; approval MIX1 returned `approved` after 27.741 s. The manual-action subagent explicitly stopped its dependent simulated task. No real action was performed.
- Unauthorized-user live check: pending; operator has no second Telegram account available for the check.
- Duplicate live check: pending; operator has not yet tried a second direct reply to completed Q2.
- Real timeout attempt started at **2026-10-11 18:19:50.573 UTC** (**22:19:50.573 Asia/Tbilisi**), title `Real timeout — leave unanswered`. The original call returned `{"status":"approved"}` at **18:20:53.934 UTC**, after **63.361 seconds**. It received a normal approval response; it did not return `HITL_TIMEOUT` or a client timeout error. This attempt cannot establish 15–20-minute survival or the 3550-second timeout. Elapsed measurements in this session use the orchestration clock's wall time; no monotonic elapsed measurement is claimed.

Do not mark the full live acceptance complete while unauthorized-user, duplicate, or timeout observations are missing. A response before 3550 seconds proves survival only up to the measured duration, not the server timeout or full client budget.

The operator chose a separate **15–20-minute connection-survival check**, followed by a normal approval, instead of a full unanswered wait in this session. That call started at **2026-10-11 18:21:37.139 UTC** (**22:21:37.139 Asia/Tbilisi**), title `Connection survival — wait 15–20 minutes`. The original call returned `{"status":"approved"}` at **18:37:39.065 UTC** (**22:37:39.065 Asia/Tbilisi**), after **961.926 seconds (16 minutes 1.926 seconds)**, with `isError: false`. The same invocation stayed pending throughout; no retry, simulated time, server restart, or shortened production timeout was used. **PASS for the requested 15–20-minute connection-survival check.** This establishes survival for the observed duration only. Task 6.4 remains incomplete unless a full unchanged 3550-second wait later returns `HITL_TIMEOUT`.

## Operator archive acceptance, 2026-10-11

The operator explicitly confirmed: “Sync now. mark task 6.4 as approved, 6.3 as skipped”. The MVP is accepted for archive with task 6.3 skipped and task 6.4 approved by acceptance exception. This decision does not establish a full-duration timeout PASS: only 961.926 seconds of connection survival followed by `approved` was measured. Live duplicate/unauthorized-user checks and the actual 3550-second `HITL_TIMEOUT` remain unverified and deferred. Production timeout and behavior requirements remain unchanged.
