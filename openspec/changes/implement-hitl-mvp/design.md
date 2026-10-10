# Design

## Context

See `proposal.md` for motivation and `specs/` for the acceptance contracts. Discovery found only documentation, OpenSpec configuration, and workflow skills: there are no application modules, dependencies, tests, or container files to extend. There are no existing OpenSpec main specs. `docs/project.md`, referenced by configuration, is absent; the README and three component documents are the available product contract. The working directory is not currently a Git repository.

This design is necessary because the change spans two services, an MCP transport, and a Telegram integration. Python, the MCP Python SDK, FastAPI, one process per service, RAM-only pending state, long polling, and two Compose containers are prescribed by the docs.

## Goals / Non-Goals

**Goals:**
- Keep correlation and completion authority in MCP, with a bot that derives correlation from Telegram messages.
- Make async lifecycle races deterministic and testable without changing the production timeout.
- Separate transport adapters from request and response validation so behavior can be tested without live Telegram credentials.

**Non-Goals:**
- No persistence, delivery retries/reconciliation, message recovery, or additional services.
- No new user cancellation endpoint; cleanup covers cancellation that reaches the running call.
- No identity-discovery mechanism or extension of the three-field public tool schema.
- No claim that the documented 3600-second Codex limit or long-running transport behavior has already been verified.

## Decisions

### 1. Package two applications and small shared contracts

Proposed structure: `src/codex_hitl/contracts.py`, `config.py`, `mcp_server/`, and `telegram_bot/`, with tests under `tests/` and the deployable agent skill at `skills/hitl/SKILL.md`. Use one Python project definition and pin the dependencies selected during implementation. Use asynchronous HTTP clients for internal calls and Telegram Bot API requests. This keeps one repository while allowing each service to start separately; separate repositories or a common runtime process would conflict with the documented deployment boundary.

Serve the SDK's HTTP MCP transport at exactly `/mcp`, alongside FastAPI's internal answer route, under one ASGI application and one worker. Explicitly register the tool name `hitl.request` and inspect its generated schema. Compose the SDK and FastAPI lifespan handling so the SDK transport is initialized and shut down correctly. The bot's lifespan starts and cancels its one polling task. Avoid implementing JSON-RPC manually; the SDK owns MCP protocol details. Verify the selected SDK APIs and route mounting when implementing rather than assume a particular release's helper signatures.

### 2. Define strict boundary models and a shared token convention

Public input has exactly `type`, `title`, and `description`; forbid extra fields and do not add undocumented title/text restrictions. Internal message payload is `{request_id, type, title, description}` and its response contains `message_id`. Internal answer payload is `{request_id, answer}`, where `answer` is one of the result objects documented in `docs/MCP_SERVER.md`. Successful answer handling returns `{accepted: true|false}`.

Use `Authorization: Bearer <INTERNAL_API_TOKEN>` for both internal endpoints, checking it before processing the payload. This header convention is a proposed implementation choice because the docs specify a token but no encoding. Distinguish malformed payloads (HTTP validation error) from structurally valid answers incompatible with an active request (`accepted: false`). Authentication failures must not touch lifecycle state or send messages. Keep tokens out of logs and examples.

### 3. Let a single event loop serialize completion

Keep `pending[UUID] = (Future, request_type)` in the MCP process. Register before calling the bot, so a fast Telegram answer is not lost. After delivery succeeds, await the Future for 3550 seconds. A `finally` block always removes the exact registered entry and cancels an unresolved Future. Delivery failures surface as an MCP tool error rather than an undocumented success-shaped result.

Answer handling checks existence, `future.done()`, `future.cancelled()`, and compatibility with the recorded type, then sets the result without an intervening `await`. A single event loop makes this check-and-complete region atomic; a second answer observes a finished Future even before final cleanup. An async lock would also work but is unnecessary if this region remains synchronous. Document and test that invariant to prevent a future refactor from inserting a suspension point. Multiple workers would each have different registries and are unsupported.

Use a bounded bot-delivery HTTP operation (proposed total budget: 10 seconds) so delivery does not consume the margin before the documented client limit. The 3550-second wait starts after successful delivery, following the source sequence. Cancel and clean up on delivery timeout. This is a delivery-error boundary, not a shortened HITL wait. No automatic retry is made when delivery may have succeeded remotely.

### 4. Carry Telegram correlation in bot-authored messages

Render plain text with a canonical first-line request marker containing UUID and type, followed by title and description. Place the marker outside user-provided text and parse only that canonical location. Encode button callback data as a compact action plus UUID (for example `approve:<uuid>`); map only known actions to documented result statuses. No request-to-message registry is needed.

For direct replies, verify the original message belongs to this bot and contains a valid marker before parsing it. Verify the sender against `TELEGRAM_ALLOWED_USER_ID` before any forwarding or deletion. Forward a question's direct text reply as `{status: answered, answer: <text>}`. For authorized text replies to approval/manual-action messages, call Telegram deletion and do not forward, even if deletion fails. A deletion failure is an operational error, not permission to accept text.

For callbacks, acknowledge the callback to Telegram, forward the mapped result to MCP, and remove the original inline keyboard only after confirmed acceptance. A keyboard-edit failure does not reverse an accepted decision; MCP still rejects duplicates. Notify the user on inactive requests or failed answer forwarding. Do not retry ambiguous answer delivery. Ordinary uncorrelated messages and unsupported updates do not complete requests.

Use one `getUpdates` loop with an in-memory offset, advancing past handled updates, and a client timeout that accommodates the chosen long-poll duration. No webhooks or durable update offsets are added. Telegram API failures must not silently kill the polling task; log operational failures and continue polling with bounded backoff. This polling resilience does not retry failed business-message delivery.

### 5. Preserve the identity boundary

The current public tool provides no name or role, and the docs explicitly defer their source and transport. This MVP therefore receives no identity and renders no fabricated identity. The conditional display requirement remains recorded in the Telegram spec for a separately authorized identity-propagation change. Do not infer identity from the title, environment, or parent agent and do not add optional public fields here.

### 6. Keep deployment configuration explicit

Provide two Docker build targets or Dockerfiles, `compose.yaml`, and a secret-free `.env.example`. Use the documented bot variables and a proposed `BOT_API_URL` for MCP-to-bot connectivity. Use Compose service names for internal addresses, publish the MCP listener for the Codex client, and keep the bot listener internal. Start one ASGI worker per container. Configuration loading should fail clearly on missing credentials or invalid numeric user/chat settings rather than run partially configured.

Document installing `skills/hitl/SKILL.md`, configuring Codex for the HTTP endpoint and the documented call budget, starting/stopping Compose, and running tests. Installation into a user's global skill directory or mutation of their Codex configuration is an operator step, not an automatic application side effect. Exact client-setting syntax must be checked against the installed client during implementation.

### 7. Test through adapters and the real MCP protocol

Use pytest with async support, in-process ASGI clients, mocked Telegram HTTP responses, and the SDK client for transport tests. Cover schema exposure, all five successful result statuses, concurrency, competing answers, wrong types, unknown identifiers, timeout, delivery errors, and cancellation cleanup. Drive timeout tests with a controlled clock or a patched wait primitive that records the requested 3550 seconds; do not introduce a runtime timeout override.

Bot tests cover message controls, UUID/type markers, callback mapping, authorized-user filtering, direct replies, forbidden text deletion, forwarding errors, and post-acceptance keyboard edits. Integration tests connect both service applications with a Telegram test double, proving that each response resolves its original MCP invocation. A separate operator-run smoke procedure uses real Codex and Telegram to verify tool discovery, a decision, a text answer, manual action, and concurrent root/subagent use when available. Agent behavior itself requires a scenario review/live exercise; static skill tests alone cannot prove reasoning behavior.

## Risks / Trade-offs

- Long-lived SDK/HTTP/client connections may time out before the internal limit → verify the actual selected SDK and client setup with a live call; treat 3600 seconds as a documented assumption until measured.
- Restart destroys pending calls and bot update offsets → document this intentional RAM-only limitation and test rejection of old identifiers; do not add persistence.
- Telegram may accept a message or answer before a network failure hides its result → report failure and clean up as specified; recovery remains outside scope.
- Telegram limits or permissions can reject long messages, message deletion, or keyboard edits → surface/log the failure and preserve server-side completion rules; do not silently truncate or accept forbidden input.
- A disconnect may not propagate immediate cancellation through the selected SDK → test cancellation that reaches the coroutine and document observed disconnect behavior; the fixed timeout still bounds the response wait.
- Optional identity display cannot be exercised end to end yet → record the missing transport and keep the current schema intact.

## Migration Plan

There is no existing implementation or data to migrate. Build both images, supply local secrets, start the two services, run automated integration checks, then register the MCP endpoint and install the skill for a live smoke test. Record actual Codex/Telegram validation separately from automated test results. Roll back by stopping the containers and removing the local client/skill registration; pending requests are intentionally lost on shutdown.
