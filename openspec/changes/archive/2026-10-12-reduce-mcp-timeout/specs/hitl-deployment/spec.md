# Spec Delta

## ADDED Requirements

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
