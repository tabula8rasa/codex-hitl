# MCP HITL — MVP Specification

## Purpose

Receive requests from Codex, wait for the user's decision, and return the result to **the original MCP call**.

## Interfaces

- `POST /mcp` — MCP transport (including `tools/call`); handled by the MCP Python SDK.
- MCP tool `hitl.request(type, title, description)` — the agent's only tool.
- `POST /internal/answer` — response from the Telegram bot: `request_id`, `answer`; server response: `accepted: true/false`.

Allowed types: `approval`, `question`, `manual_action`.

## Functions

**`hitl_request(type, title, description)`**
1. Validates arguments against the tool schema.
2. Generates a UUIDv4 and creates an `asyncio.Future`.
3. Registers `pending[request_id] = (future, type)`.
4. Executes `await send_to_bot(...)` — `POST /internal/messages`.
5. Executes `await future` with an internal timeout of 3550 seconds.
6. Returns the response or `HITL_TIMEOUT` to the agent; always removes the entry from `pending`.

**`receive_answer(request_id, answer)`**
1. Verifies authorization of the internal request.
2. Finds the active Future in `pending`.
3. If the request is active, calls `set_result(answer)` and returns `accepted: true`; otherwise returns `false`.

## Results

- `{"status":"answered","answer":"..."}` — text response.
- `{"status":"approved"}` / `{"status":"rejected"}` — authorization decision.
- `{"status":"completed"}` / `{"status":"unable"}` — manual action.
- `{"status":"timeout","error_code":"HITL_TIMEOUT"}` — timeout expired.

## Constraints

- Python, MCP Python SDK, FastAPI (internal HTTP API), Docker.
- A single MCP process; multiple concurrent requests via `asyncio`.
- No SQLite/Redis: active requests exist only in `pending` (RAM).
- HITL wait timeout: **3550 seconds**; Codex call limit: **3600 seconds**.
- If sending the message fails, the call terminates with an error and cleans up `pending`.
- Pending calls are lost when the server restarts. Expired/unknown responses are rejected.
- Internal HTTP calls are protected by `INTERNAL_API_TOKEN`.

## Additional Requirements for the Request Lifecycle

- The first valid response wins: only one response per request can receive `accepted: true`.
- The server checks that the request is still active, the Future has not completed or been canceled, and the response matches the original request type: `approved` / `rejected` for `approval`, `answered` with a text `answer` for `question`, and `completed` / `unable` for `manual_action`.
- Checking request activity and accepting a response must prevent two competing responses from being accepted. Duplicate, late, and type-mismatched responses do not complete the Future and receive `accepted: false`.
- A completed or canceled request cannot be reopened. This rule does not define a new cancellation interface; how cancellation is initiated remains a separate design question.
- After `accepted: true`, the bot removes the message buttons. Removing the buttons does not replace server-side validation of duplicate responses.

## Additional Context and Constraints

- The existing `hitl.request(type, title, description)` schema remains unchanged until a separate decision is made on transmitting identity information.
- The wait timeout remains **3550 seconds**. A shorter timeout considered for future testing does not change the current contract.

## Running the implementation

Install the project and its test dependencies with `python -m pip install -e '.[test]'`.
Set `INTERNAL_API_TOKEN` to a shared secret and `BOT_API_URL` to the bot service's
base URL (for Compose, `http://bot:8101`). Start one process:

```sh
uvicorn codex_hitl.mcp_server:create_app --factory --host 0.0.0.0 --port 8100 --workers 1
```

The MCP Python SDK owns Streamable HTTP and JSON-RPC at exactly `/mcp`. The
application manages the SDK session manager in its lifespan. Each HTTP request
uses stateless SDK transport; the request lifecycle remains in this one process's
RAM, independently of transport sessions. Run **one worker**: multiple workers
would have separate registries and cannot route answers reliably. There is no
database, cancellation endpoint, response timeout setting, or delivery retry.

Internal delivery is `POST ${BOT_API_URL}/internal/messages` with
`Authorization: Bearer <INTERNAL_API_TOKEN>` and this JSON shape:

```json
{"request_id":"74e0b09d-c44b-4501-bbed-ceaa49acfe32","type":"approval","title":"Deploy?","description":"Authorize deployment."}
```

The bot returns `{"message_id":123}`. The reciprocal `POST /internal/answer`
uses the same Bearer header and, for example:

```json
{"request_id":"74e0b09d-c44b-4501-bbed-ceaa49acfe32","answer":{"status":"approved"}}
```

Question answers instead contain `{"status":"answered","answer":"text"}`;
manual actions contain `completed` or `unable`. All boundary models forbid extra
fields and identifiers must be canonical UUIDv4 strings. Missing/wrong tokens
return HTTP 401. Malformed answer objects return HTTP 422; a structurally valid
but incompatible or inactive answer returns `{"accepted":false}`. Only the first
valid answer returns `{"accepted":true}`. The activity check and Future completion
run synchronously without suspension within one event loop.

Delivery has a **10-second total budget**, in addition to HTTP operation timeouts.
HTTP failures, invalid delivery responses, and delivery timeouts return MCP tool
errors and clean up the registered Future. An ambiguous outcome is not retried.
Error text omits remote response bodies and credentials. After successful delivery,
the original call waits **3550 seconds** and returns the documented timeout shape
if unanswered. Cancellation reaching the running coroutine cleans up its request;
shutdown cancels unresolved Futures. Restart loses all pending state.

The documented 3600-second Codex client budget and propagation of real client
network disconnects still require the operator-run live checks. Unit cancellation
tests verify coroutine cancellation, not every client's disconnect behavior.

## Component verification and test adapters

```sh
python -m pytest tests/test_mcp*.py -q
```

These tests use the real SDK client over in-process ASGI HTTP for discovery,
validation and returned results, plus controlled async lifecycle tests for races,
out-of-order requests, all result statuses, authorization, errors and cleanup.
They assert the unchanged 3550-second response wait and 10-second delivery budget
through patched timing primitives, without waiting an hour or adding a runtime
override.

`create_app(config, bot_client=client)` accepts an externally owned async HTTP
client, which tests can route through `httpx.MockTransport` or `ASGITransport`.
The app does not close injected clients. `app.state.service` exposes the
`RequestService` and its `pending` map for assertions. Timeout tests patch the
module-local `codex_hitl.mcp_server.lifecycle.wait_for`; delivery-budget tests can
patch its `timeout` context manager. The `sdk_session` helper in
`tests/test_mcp_sdk.py` shows correct lifespan and SDK client setup. These seams
are test adapters, not public HTTP or MCP interfaces.

The MCP transport explicitly enables the SDK's DNS-rebinding protection. Its
Host allowlist permits only `localhost`, `127.0.0.1`, and `[::1]`, with optional
ports; supplied Origin headers must use HTTP and one of those loopback hosts.
Non-browser SDK clients may omit Origin. Invalid Host returns HTTP 421 and
invalid Origin returns HTTP 403 before tool execution. Deployment still publishes
the listener only on loopback. In-process SDK tests use
`http://127.0.0.1:8100/mcp`, so they exercise the production allowlist.
