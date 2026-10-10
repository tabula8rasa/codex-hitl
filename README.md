# Codex HITL — MVP

## Goal

Enable Codex and its subagents to request a decision from the user and resume work after receiving a response. The user interacts through Telegram.

## Components

1. **Skill `hitl`** — instructs the agent when and how to invoke `hitl.request`.
2. **MCP HITL Server** — receives the call, creates a UUID and a `Future`, waits for the response, and returns it to the same Codex call.
3. **Telegram Bot Server** — sends a message with the appropriate buttons, receives the user's response, and forwards it to MCP.

One repository, two Docker containers (MCP and Bot), launched with Docker Compose.

## Flow

```text
Codex → POST /mcp → hitl.request(type, title, description)
                   → UUID + pending[UUID] = Future
                   → POST Bot /internal/messages
                   → Telegram → user
                   ← POST MCP /internal/answer
                   ← Future.set_result(answer)
Codex ← result of the original call
```

## MVP Rules

- Request types: `approval`, `question`, `manual_action`.
- The agent provides only three input fields; it does not know about UUIDs, Telegram, or the waiting mechanism.
- MCP waits for a maximum of **3550 seconds**; Codex has a **3600-second** limit.
- On `HITL_TIMEOUT`, the subagent stops the blocked work and reports the error to its parent agent; the parent decides what to do next.
- All active requests are stored in RAM, without SQLite, Redis, or queues.
- Pending requests are lost when MCP restarts. A late response is rejected after the request has ended.
- Internal HTTP interfaces are protected by a token; Telegram responses are accepted only from the authorized user.

## Specification Files

- `SKILL.md` — agent behavior.
- `MCP_SERVER.md` — MCP interfaces and waiting mechanism.
- `TELEGRAM_BOT.md` — bot interfaces and behavior.
- `README.md` — overall MVP contract.

**Status:** The specification has been agreed upon; the code has not yet been implemented, and integration with Codex has not been tested.

## Additional Agreed Decisions

1. The first valid response is accepted as final. A completed or cancelled request cannot be reopened.
2. For a `question` request, the user responds with text by replying directly (`reply_to_message`) to the corresponding Telegram message.
3. The bot ignores and deletes text replies to messages of types `approval` and `manual_action`; such replies do not complete the request.
4. After the MCP server confirms that it has accepted the response, the bot removes the buttons from the corresponding Telegram message.
5. Delivery recovery and handling of ambiguous delivery outcomes are outside the scope of the current MVP.
6. The **3550-second** timeout remains unchanged. Reducing the timeout when testing the working implementation is a future decision and does not modify the current specification.
