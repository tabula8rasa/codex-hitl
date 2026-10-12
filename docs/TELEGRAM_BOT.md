# Telegram Bot HITL — MVP Specification

## Purpose

Receive a request from HITL, display it to the user, and send the response back. The bot does not store pending-request states or control Codex.

## Interfaces

- `POST /internal/messages` — receives `request_id`, `type`, `title`, and `description` from MCP; returns `message_id`.
- Telegram Bot API `getUpdates` — Long Polling for new events.
- `POST /internal/answer` — the bot sends `request_id` and `answer` to MCP; receives `accepted: true/false`.

## Functions

- **`send_message(...)`** — constructs the text and buttons based on the request type, sends the message, and returns `message_id`.
- **`poll_updates()`** — receives Telegram events and passes them to the handler.
- **`handle_update(update)`** — verifies the authorized user; extracts `request_id` from a button or the message being replied to; constructs the response.
- **`send_answer_to_mcp(...)`** — sends the response to HITL and notifies the user if the request is no longer active or delivery fails.

## Request Types

| Type | User Interface | Result |
|---|---|---|
| `approval` | “Approve” / “Reject” | `approved` / `rejected` |
| `question` | Text reply to the message | `answered` + `answer` |
| `manual_action` | “Done” / “Unable” | `completed` / `unable` |

## Constraints

- Python, FastAPI, Telegram Bot API, separate Docker container.
- No database or webhooks; a single Long Polling process.
- The request identifier is included in `callback_data` or in the original message text for `reply_to_message`.
- Accepts responses only from `TELEGRAM_ALLOWED_USER_ID`.
- Internal calls are protected by `INTERNAL_API_TOKEN`.
- Configuration: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_USER_ID`, `HITL_API_URL`, `INTERNAL_API_TOKEN`.

## Additional Requirements for Messages and Response Handling

- The message includes the agent's name (`agent_name`) and role (`agent_role`) when these details are available. How they are obtained and passed through has not yet been defined; the bot must not invent a missing name or role.
- For `question`, only a direct text reply (`reply_to_message`) to the corresponding bot message is accepted. Ordinary text without this reference is not treated as a response to the request.
- For `approval` and `manual_action`, only the corresponding button presses are accepted. A text reply from the authorized user to such a message is ignored and deleted from the chat; it is not forwarded to MCP and does not complete the request.
- The MCP server definitively accepts the first valid response. Completed or canceled requests cannot be reopened; the bot does not create a new pending request when someone responds again to an old message.
- After receiving `accepted: true` from MCP, the bot removes the inline buttons from the corresponding Telegram message. An authenticated expiry notification also removes buttons, explicitly indicating expiry rather than accepted completion.
- Delivery recovery and ambiguous delivery outcomes are outside the scope of the current MVP; the existing notification to the user about failed delivery or an inactive request remains in place.

## Running the implemented service

Use Python 3.12+ and the repository's installed dependencies. Set all five required variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (an integer, including negative group IDs), `TELEGRAM_ALLOWED_USER_ID` (a positive integer), `HITL_API_URL` (the MCP service base URL), and `INTERNAL_API_TOKEN`. For example, the Compose internal MCP base URL is `http://mcp:8100`. Missing or invalid configuration fails startup. Keep credentials outside version control.

```bash
uvicorn codex_hitl.telegram_bot:create_app --factory --host 0.0.0.0 --port 8101 --workers 1
```

`POST /internal/messages` requires `Authorization: Bearer <INTERNAL_API_TOKEN>` and exactly the four documented message fields. Authentication runs before delivery. Validation failures return HTTP 422; failed or malformed Telegram delivery returns HTTP 502 with a safe error message. Outgoing MCP answers use the same Bearer token and append `/internal/answer` to `HITL_API_URL`.

## Correlation and polling

Plain-text request messages start with the canonical line `HITL <canonical-uuidv4> <approval|question|manual_action>`, before the title and description. Buttons carry `approve:<uuid>`, `reject:<uuid>`, `done:<uuid>`, or `unable:<uuid>`. Only the first line is parsed; marker-like user text elsewhere cannot override correlation. No HTML or Markdown parse mode is used.

Startup calls Telegram `getMe` and verifies bot identity before creating one polling task. Original messages must be authored by that verified bot, be in the configured chat, and carry a valid marker. Callbacks must match both the marker UUID and request type. Incoming reply/callback users must match the allowed user. Questions accept direct text replies only; authorized text replies to button requests are deleted, even if deletion fails operationally. Uncorrelated or unauthorized updates have no business effects.

The lifespan cancels and awaits the polling task on shutdown. `getUpdates` uses a 30-second long poll within a 40-second HTTP/operation budget. Update offsets exist only in RAM and advance after processing each update. Restart loses the offset; MCP remains the authority for rejecting repeated or old answers. Transient polling failures are logged without credential-bearing exception details and use bounded backoff of at most 30 seconds. No pending-request registry, webhook, database, or retry of business delivery is added.

## Failures and acceptance

Telegram business operations and answer forwarding each have a 10-second total operation budget. The bot acknowledges recognized authorized callbacks, forwards the response once, and removes buttons after MCP returns `accepted: true`. Authenticated expiry notifications independently remove buttons and annotate the original message as expired. An inactive request triggers a user notification without removing buttons. Answer forwarding failure triggers a notification stating that acceptance could not be confirmed; it is never retried automatically. If a notification, deletion, acknowledgment, or keyboard edit fails, an operational warning is logged and polling continues. A keyboard-edit failure cannot reverse MCP acceptance. Telegram message-size or permission failures are surfaced without silent truncation. Live delivery and permissions require operator verification.

Agent identity transport remains explicitly deferred. The strict current internal/public contracts do not carry agent name or role, so messages display neither and invent neither.

## Component tests and test seams

```bash
.venv/bin/python -m pytest tests/test_telegram.py -q
```

`create_app(config=None, *, telegram_client=None, mcp_client=None, telegram_api_url="https://api.telegram.org")` accepts injected `httpx.AsyncClient` instances and a Telegram API base URL for deterministic tests. The bot appends `/bot<token>/<method>` to that base URL. Injected clients are caller-owned and remain open after lifespan shutdown; clients created by the factory are closed by the lifespan. Production startup uses the fixed Telegram URL; the alternate URL is a constructor test seam, not an environment setting.

`app.state.bot` provides the `TelegramBot` adapter for tests. Entering the application lifespan exercises actual `getMe`, polling, and managed cancellation. Tests that exercise handlers directly can call `await app.state.bot.initialize()` before `handle_update(update)` without launching a second poller. Mock transports can inspect all Telegram JSON and internal Bearer headers. Automated tests cover message formatting, authentication, bot/chat/user correlation, all five valid answer statuses, ignored inputs, deletion failure, forwarding failure, confirmed button removal, duplicate rejection notifications, polling offsets/backoff, concurrent start prevention, and shutdown. These mocked checks do not replace a live Telegram/Codex smoke test.

## Automatic expiry updates

Authenticated `POST /internal/expire` accepts exactly `message_id` (a positive integer) and `message` (the original `request_id`, `type`, `title`, and `description`). It uses only the configured chat. Missing/wrong internal credentials return 401 and invalid payloads return 422 before Telegram effects. The success response is `{"updated":true}`; failed edits return HTTP 502 with safe detail `Telegram expiry edit failed`.

For approval, manual-action, and question requests, the bot reconstructs the original text with the same renderer, appends two newlines and exactly `This request is no longer active. Your answer was not accepted.`, and calls `editMessageText` with the original message ID and an empty inline keyboard. Questions retain their direct-reply instruction. No user click or separate expiry message is needed; no pending-state registry is introduced. Repeated notifications produce the same final text, and Telegram's specific already-unmodified response counts as success. Other editing failures (deleted message, size, permissions, transport/API errors) are logged safely and surfaced without retry, truncation, or false success. Late answers still receive the existing inactive notification.

Verify endpoint authentication/validation, all request types, idempotency, and failure handling with `.venv/bin/python -m pytest tests/test_expiry.py tests/test_telegram.py -q`.
