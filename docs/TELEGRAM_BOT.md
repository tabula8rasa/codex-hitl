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
- After receiving `accepted: true` from MCP, the bot removes the inline buttons from the corresponding Telegram message. Before MCP confirms acceptance, the buttons must not be removed as an indication that the response was accepted.
- Delivery recovery and ambiguous delivery outcomes are outside the scope of the current MVP; the existing notification to the user about failed delivery or an inactive request remains in place.
