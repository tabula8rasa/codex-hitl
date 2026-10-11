# Tasks

## 1. Python foundation and internal contracts

- [x] 1.1 Create the `src/codex_hitl` package, separate MCP/bot entry points, project dependencies, and async pytest setup; verify a clean dependency installation and import of both application factories.
- [x] 1.2 Implement strict request, internal message, answer, and result models; add parameterized tests for all request types, five valid answer statuses, missing/extra fields, missing question text, and type mismatches.
- [x] 1.3 Implement service-specific environment loading and shared Bearer-token authentication; verify automated tests reject absent/incorrect tokens before effects and reject missing credentials or invalid numeric configuration.
- [x] 1.4 Document internal payload shapes, Bearer header convention, and the proposed `BOT_API_URL` in the component docs; verify examples match the tested models without changing the existing public schema.

## 2. MCP tool and request lifecycle

- [x] 2.1 Compose the SDK HTTP transport and FastAPI answer endpoint with correct lifespan handling at `/mcp`; verify an SDK-client test discovers exactly `hitl.request` with only the three documented input fields and rejects invalid calls before delivery.
- [x] 2.2 Implement UUIDv4 registration before bot delivery and return results through the original call; verify async tests cover all five valid result statuses, out-of-order concurrent answers, and an answer arriving before delivery returns.
- [x] 2.3 Implement the authenticated answer route with synchronous check-and-complete handling; verify competing responses yield exactly one acceptance and duplicate, unknown, finished, canceled, or type-mismatched answers return `accepted: false`.
- [x] 2.4 Implement the fixed 3550-second response wait, bounded delivery operation, and terminal cleanup; verify controlled-time tests assert the production wait value and cover timeout results, late answers, delivery errors/timeouts, cancellation, and loss of pending state in a new server instance.
- [x] 2.5 Update `docs/MCP_SERVER.md` with startup instructions, error behavior, single-worker invariant, and lifecycle-test command; verify the documented command passes and no cancellation API, persistence, or timeout override was introduced.

## 3. Telegram rendering and response handling

- [x] 3.1 Implement authenticated message creation, canonical UUID/type message markers, controls for all three request types, and `message_id` responses; verify mocked Telegram tests cover rendering, marker round trips, no fabricated identity, unauthorized requests, and send failures.
- [x] 3.2 Implement one long-polling task with in-memory update offsets and managed shutdown; verify tests cover multiple updates, transient polling errors, and cancellation without creating a second poller or a pending-request registry.
- [x] 3.3 Implement authorized callback mapping and direct-question text replies, validating the original bot message marker; verify tests reject unauthorized senders, malformed callbacks, unrelated messages, uncorrelated text, and non-text question replies.
- [x] 3.4 Implement deletion of authorized text replies to approval/manual-action messages; verify tests assert deletion is attempted and no answer is forwarded, including when Telegram deletion fails.
- [x] 3.5 Implement answer forwarding, callback acknowledgments, notifications, and removal of buttons only after `accepted: true`; verify tests cover acceptance, inactivity, forwarding failure, keyboard-edit failure, and a repeated response without reopening the request.
- [x] 3.6 Update `docs/TELEGRAM_BOT.md` with configuration, correlation format, operational failure behavior, and bot-test command; verify the command passes and identity propagation remains explicitly deferred.

## 4. Agent skill delivery

- [x] 4.1 Create `skills/hitl/SKILL.md` from the agreed skill contract and document local installation; verify a scenario review covers necessary escalation, independent resolution, the exact three-field call, rejection, unconfirmed manual action, parent/root error reporting, and no automatic retry.
- [x] 4.2 Add automated checks for the delivered skill's frontmatter and required contract instructions; verify these checks pass and document that they validate the artifact rather than prove agent reasoning behavior.

## 5. Container deployment

- [x] 5.1 Add MCP and bot Docker images, `compose.yaml`, and a secret-free `.env.example` with internal service URLs; verify `docker compose config` resolves two services with one worker each and no database, queue, or webhook dependency.
- [x] 5.2 Document build/start/stop commands, local MCP exposure, skill installation, client connection configuration, the fixed wait budget, and restart limitations; verify both images build and the documented local endpoints match the application routes.
- [x] 5.3 Add deployment configuration checks for required variables, internal Bearer-token use, and service connectivity; verify automated checks and a container startup smoke test with a Telegram test double pass without real secrets.

## 6. Cross-service and client verification

- [x] 6.1 Add integration tests using an SDK client, both application instances, and a Telegram test double; verify all three request types resolve the original calls, including parallel requests answered out of order, and run the full automated suite.
- [x] 6.2 Add cross-service failure tests for unauthorized answers, forbidden text replies, duplicate responses, expired requests, and bot delivery failures; verify pending state is cleaned up and no unaccepted answer resolves a call.
- [-] 6.3 **Skipped by operator at archive on 2026-10-11.** Write and execute the operator-run Codex/Telegram smoke procedure with configured credentials, covering tool discovery, approval, question, manual action, and concurrent root/subagent requests when supported; record observed results and any client/SDK timeout or disconnect limitations, leaving this task incomplete if live access is unavailable.
- [x] 6.4 **Approved by operator acceptance exception at archive on 2026-10-11; not a verified full-timeout PASS.** Exercise the live long-running call budget with the unchanged 3550-second server wait and record whether the configured client returns `HITL_TIMEOUT` before its documented 3600-second limit; do not mark complete based only on accelerated automated tests or lower the production timeout.

## Archive acceptance decision

On 2026-10-11 the operator explicitly selected: “Sync now. mark task 6.4 as approved, 6.3 as skipped”. Task 6.3 is retained with a skipped marker, which the CLI counts as incomplete. Task 6.4 is checked to record operator approval of MVP acceptance with an exception, not successful execution of its original full-duration verification. The observed connection-survival result was 961.926 seconds followed by `approved`; a live 3550-second `HITL_TIMEOUT` was not observed. Remaining live duplicate/unauthorized-user checks and full-duration timeout verification are deferred. The production timeout and specifications are unchanged.
