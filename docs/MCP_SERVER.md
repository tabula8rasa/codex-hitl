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
