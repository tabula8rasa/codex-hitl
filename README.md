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

**Status:** MVP accepted by the operator and OpenSpec change [archived](openspec/changes/archive/2026-10-11-implement-hitl-mvp/). Implementation, automated tests, deployment assets, and the HITL skill are present. Main capability contracts are in `openspec/specs/`. Verification evidence and the operator-approved exceptions for remaining live checks are recorded in `docs/VERIFICATION.md`.

## Additional Agreed Decisions

1. The first valid response is accepted as final. A completed or cancelled request cannot be reopened.
2. For a `question` request, the user responds with text by replying directly (`reply_to_message`) to the corresponding Telegram message.
3. The bot ignores and deletes text replies to messages of types `approval` and `manual_action`; such replies do not complete the request.
4. After the MCP server confirms that it has accepted the response, the bot removes the buttons from the corresponding Telegram message.
5. Delivery recovery and handling of ambiguous delivery outcomes are outside the scope of the current MVP.
6. The **3550-second** timeout remains unchanged. Reducing the timeout when testing the working implementation is a future decision and does not modify the current specification.

## First-time setup

You need Docker with Docker Compose, Python 3.12+ for the setup helper, a Telegram account, and Codex running on the same machine as the containers. Run terminal commands from the cloned repository directory. Python application dependencies are installed inside the images; a local virtual environment is only needed for development/tests.

### 1. Create a Telegram bot

Open [@BotFather](https://t.me/BotFather), send `/newbot`, and follow the prompts to choose a name and username. Save the bot token it gives you. Treat it as a password and keep it out of Git and chat messages. See the [official Telegram tutorial](https://core.telegram.org/bots/tutorial).

Open your new bot's private chat, press **Start**, and send `hello`. Use a private chat for this initial setup.

### 2. Get your chat ID and Telegram user ID

Before starting the containers, run this helper. It asks for the bot token without displaying it and prints IDs from messages sent to the bot:

```bash
python3 - <<'PYTHON'
import getpass
import json
import urllib.request

bot_token = getpass.getpass("Telegram bot token: ")
url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
with urllib.request.urlopen(url, timeout=10) as response:
    data = json.load(response)
for update in data.get("result", []):
    message = update.get("message", {})
    if "from" in message and "chat" in message:
        print("TELEGRAM_CHAT_ID =", message["chat"]["id"])
        print("TELEGRAM_ALLOWED_USER_ID =", message["from"]["id"])
PYTHON
```

If nothing prints, send another message to your bot and rerun. Use the IDs from your own message. In a private chat, the chat ID and user ID are usually the same. This helper uses Telegram's [getUpdates API](https://core.telegram.org/bots/api#getupdates); do not run it alongside another poller for the same bot. For an existing bot, stop its other polling process first; this project uses long polling and requires no active webhook.

### 3. Configure the local environment

Create the local configuration once; if `.env` already exists, edit it instead of overwriting it:

```bash
cp .env.example .env
chmod 600 .env
```

Generate a random token for authentication between the two services:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Edit `.env` and fill in all four values:

```dotenv
INTERNAL_API_TOKEN=the_random_token_you_generated
TELEGRAM_BOT_TOKEN=the_token_from_BotFather
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ALLOWED_USER_ID=your_user_id
```

Replace the placeholders with actual values. Keep `.env.example` blank; credentials belong only in the ignored `.env`. Compose supplies `BOT_API_URL=http://bot:8101` and `HITL_API_URL=http://mcp:8100` automatically.

### 4. Build and start the services

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
```

Both `mcp` and `bot` should be running. MCP is available at `http://127.0.0.1:8100/mcp`; the bot listens internally on port **8101**. Both services use `restart: unless-stopped`, one Uvicorn worker, and an unprivileged user. Run only one polling instance for this Telegram bot.

For continuing logs or stopping the deployment:

```bash
docker compose logs -f
# Ctrl+C exits log viewing; the containers keep running.
docker compose down
```

### 5. Register the MCP server in Codex

Add or update this entry in `~/.codex/config.toml`. Preserve other settings and avoid creating a duplicate `[mcp_servers.hitl]` table:

```toml
[mcp_servers.hitl]
url = "http://127.0.0.1:8100/mcp"
tool_timeout_sec = 3600
```

Alternatively, `codex mcp add hitl --url http://127.0.0.1:8100/mcp` registers the URL; then edit its configuration entry to add `tool_timeout_sec = 3600`.

The timeout setting matters: the documented Codex default is 60 seconds, while this server waits up to 3550 seconds for a response. Telegram and internal service tokens stay in `.env`; they are not needed in this local MCP entry. See the official [MCP guide](https://developers.openai.com/codex/mcp) and [configuration reference](https://developers.openai.com/codex/config-reference). Registration syntax was checked with Codex CLI 0.162.1; the project's intended 3600-second client budget still requires live measurement.

### 6. Install the HITL skill

From the repository directory:

```bash
mkdir -p ~/.codex/skills/hitl
cp skills/hitl/SKILL.md ~/.codex/skills/hitl/SKILL.md
```

Restart Codex and open a new chat so it loads the MCP configuration and skill. Confirm the server exposes `hitl.request`.

### 7. Test the connection

Send this prompt to Codex:

> Use `$hitl` to send a test approval request through `hitl.request`. Title: “HITL connection test”. Description: “Please approve this test; no external action will be performed.” Wait for my Telegram response and report the result.

Click **Approve** in Telegram. Codex should receive `approved`, and the buttons should disappear.

Then send these prompts separately:

> Use `$hitl` to send a test question through `hitl.request`. Title: “HITL question test”. Description: “Which word should I use for this connection test?” Wait for my Telegram response and report the answer.

Reply **directly to the bot's question message** with text. Codex should receive `answered` with your exact text; an ordinary message without a reply reference does not answer the question.

> Use `$hitl` to send a test manual-action request through `hitl.request`. Title: “HITL manual-action test”. Description: “Please press Done to confirm this connection test; no external action is required.” Wait for my Telegram response and report the result.

Click **Done**. Codex should receive `completed`, and the buttons should disappear.

These checks establish the basic connection. Complete the separate [live smoke procedure](docs/LIVE_SMOKE.md) for rejection, authorization, concurrency, and the actual **3550-second (59 minutes 10 seconds)** timeout measurement.

## Development and automated tests

For local development, install Python dependencies (verified with Python 3.14):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock -e '.[test]'
.venv/bin/python -m pytest -q
```

The Docker E2E check is opt-in because it starts isolated containers. After building both images, run the complete automated suite, including container E2E:

```bash
RUN_DOCKER_E2E=1 .venv/bin/python -m pytest -q
```

The E2E test uses fake credentials and a Telegram test-double container, removes its containers/network afterward, and sends no real Telegram messages.

For native development, export the bot variables from `.env` plus `BOT_API_URL=http://127.0.0.1:8101` and `HITL_API_URL=http://127.0.0.1:8100`, then run these in separate terminals:

```bash
.venv/bin/uvicorn codex_hitl.mcp_server:create_app --factory --host 127.0.0.1 --port 8100 --workers 1
.venv/bin/uvicorn codex_hitl.telegram_bot:create_app --factory --host 127.0.0.1 --port 8101 --workers 1
```

## Operational constraints

Both internal routes require `Authorization: Bearer <INTERNAL_API_TOKEN>`. MCP transport validates Host and Origin against loopback addresses to prevent DNS rebinding. The public MCP listener has no application authentication; remote/proxy exposure requires separately reviewed authentication and transport allowlists.

The response wait is fixed at 3550 seconds after delivery, with a separate 10-second total delivery boundary. Do not lower the production wait to test. Restarting MCP loses all pending requests; restarting the bot loses its update offset. There is no persistence or recovery of ambiguous delivery outcomes. Client disconnect cancellation may depend on the SDK; see the verification record.

See [live smoke procedure](docs/LIVE_SMOKE.md), [verification evidence](docs/VERIFICATION.md), and [shared API contracts](docs/IMPLEMENTATION_CONTRACTS.md). Static skill checks validate its contents, not model reasoning.
