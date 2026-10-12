# hitl-deployment Specification

## Purpose

Run the MCP and Telegram services together with the process boundaries, configuration, and internal authentication required by the agreed HITL MVP.

## Requirements

### Requirement: Deploy two services with one process per role
The project SHALL provide Docker Compose deployment with one MCP container and one Telegram bot container. MCP SHALL support concurrent calls within one process. The bot SHALL run one long-polling process. Deployment SHALL require no database, queue service, or Telegram webhook.

#### Scenario: Compose deployment
- **WHEN** an operator starts the supplied Compose deployment with valid configuration
- **THEN** it starts the MCP service and Telegram bot as two containers
- **AND** the MCP service accepts concurrent requests while the bot polls Telegram

### Requirement: Authenticate internal HTTP calls
Both services SHALL require `INTERNAL_API_TOKEN` authentication on their internal HTTP interfaces and provide that token on outgoing internal calls. Missing or incorrect credentials SHALL be rejected before message delivery or request completion.

#### Scenario: Unauthorized message creation
- **WHEN** a caller invokes `POST /internal/messages` without the correct token
- **THEN** the bot rejects the call without sending a Telegram message

#### Scenario: Unauthorized answer
- **WHEN** a caller invokes `POST /internal/answer` without the correct token
- **THEN** MCP rejects the call without changing an active request

#### Scenario: Authorized internal call
- **WHEN** one service calls the other's internal endpoint with the configured token
- **THEN** the endpoint proceeds with its normal payload validation and handling

### Requirement: Configure Telegram and service connectivity
The bot SHALL use `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_USER_ID`, `HITL_API_URL`, and `INTERNAL_API_TOKEN`. Deployment SHALL configure the MCP service to reach the bot's internal message interface and allow Codex to reach `POST /mcp`.

#### Scenario: Configured message and answer path
- **WHEN** a valid request reaches MCP in the configured deployment
- **THEN** MCP can deliver it to the bot, the bot sends it to `TELEGRAM_CHAT_ID`, and an authorized response can return through `HITL_API_URL`

### Requirement: Document the Codex tool call budget
The supplied deployment instructions SHALL configure the Codex HITL MCP entry with `tool_timeout_sec = 900`. They SHALL distinguish this 900-second client budget from the fixed 850-second server response wait after delivery and the separate 10-second delivery budget.

#### Scenario: Operator registers the HITL server
- **WHEN** an operator follows either the TOML configuration example or the CLI registration instructions
- **THEN** the instructions specify `tool_timeout_sec = 900` for the HITL MCP entry

#### Scenario: Operator verifies an unanswered call
- **WHEN** an operator follows the current live timeout procedure
- **THEN** it requires leaving the request unanswered for the production 850-second response wait and checking for `HITL_TIMEOUT` before the 900-second client budget expires
- **AND** it requires checking that a late answer is inactive
- **AND** it requires observing removal of buttons and the exact expiry notice appended to the original Telegram message without clicking or replying first
