# telegram-hitl-interaction Specification

## Purpose

Present blocking HITL requests in Telegram and route the authorized user's correlated responses back to the waiting MCP service.

## Requirements

### Requirement: Deliver request messages with the correct controls
The bot SHALL accept authenticated `POST /internal/messages` calls with `request_id`, `type`, `title`, and `description`, send the corresponding Telegram message, and return `message_id`. Approval messages SHALL offer Approve/Reject; manual-action messages SHALL offer Done/Unable; question messages SHALL request a direct text reply.

#### Scenario: Approval message
- **WHEN** an approval request is delivered
- **THEN** the configured chat receives its title, description, and Approve/Reject buttons
- **AND** the caller receives the Telegram message identifier

#### Scenario: Manual action message
- **WHEN** a manual-action request is delivered
- **THEN** the message offers Done/Unable buttons corresponding to `completed`/`unable`

#### Scenario: Question message
- **WHEN** a question is delivered
- **THEN** its message instructs the user to reply directly with text

### Requirement: Correlate responses without a pending-state registry
The bot SHALL obtain Telegram updates through one long-polling process and SHALL correlate request identifiers from callback data or the original message text in `reply_to_message`. It SHALL NOT maintain pending-request lifecycle state or control Codex.

#### Scenario: Callback identifies a request
- **WHEN** a recognized request button is pressed
- **THEN** the bot extracts the request identifier and maps the button to the corresponding result

#### Scenario: Direct reply identifies a question
- **WHEN** a text reply references a corresponding question message
- **THEN** the bot extracts its request identifier from that original message

### Requirement: Accept responses only from the authorized user
The bot SHALL verify the sender against `TELEGRAM_ALLOWED_USER_ID` before forwarding a response to MCP.

#### Scenario: Unauthorized sender
- **WHEN** another user presses a request button or replies to a question
- **THEN** the bot does not forward an answer to MCP

### Requirement: Questions require a direct text reply
For a question request, the bot SHALL forward only a direct text reply to the corresponding bot message, using `status: answered` and the reply text as `answer`.

#### Scenario: Correlated text reply
- **WHEN** the authorized user replies directly to a question message with text
- **THEN** the bot forwards that text as an `answered` result for its request identifier

#### Scenario: Uncorrelated or non-text input
- **WHEN** the authorized user sends ordinary text without a corresponding reply reference or replies to a question with non-text content
- **THEN** the bot does not forward it as a question answer

### Requirement: Button-only requests reject text replies
Approval and manual-action requests SHALL accept only their corresponding button responses. The bot SHALL ignore and delete text replies from the authorized user to those messages without forwarding an answer or completing the request.

#### Scenario: Text reply to a button request
- **WHEN** the authorized user sends a text reply to an approval or manual-action message
- **THEN** the bot deletes that reply and does not forward it to MCP

### Requirement: Reflect confirmed acceptance and delivery failures
The bot SHALL send correlated answers to MCP and remove the original message's inline buttons after `accepted: true` or an authenticated MCP expiry notification. It SHALL notify the user if MCP reports the request inactive or answer delivery fails. Responding to an old message SHALL NOT create a new request.

#### Scenario: MCP accepts an answer
- **WHEN** MCP returns `accepted: true` for a button response
- **THEN** the bot removes the buttons from the corresponding message

#### Scenario: Answer is rejected as inactive
- **WHEN** MCP returns `accepted: false`
- **THEN** the bot notifies the user that the answer was not accepted
- **AND** it does not remove buttons as a confirmation of acceptance or create another request

#### Scenario: Answer delivery fails
- **WHEN** the HTTP call forwarding an answer fails
- **THEN** the bot notifies the user of the delivery failure without indicating accepted completion

#### Scenario: MCP announces expiry
- **WHEN** the bot receives an authenticated expiry notification for a delivered request
- **THEN** it removes that message's buttons as an indication of expiry
- **AND** it does not represent expiry as an accepted answer

### Requirement: Do not invent agent identity
When agent name and role are available, the bot SHALL include them in the message. It SHALL NOT invent a missing identity or require additional fields in the public three-field MCP tool schema.

#### Scenario: Identity is unavailable
- **WHEN** a request arrives without agent identity information
- **THEN** the bot displays the request without fabricating an agent name or role

### Requirement: Mark expired requests on their original messages
On an authenticated MCP expiry notification, the bot SHALL edit the corresponding original Telegram message, preserve its existing request text, remove all inline buttons, and append exactly `This request is no longer active. Your answer was not accepted.` as a final paragraph. This SHALL apply to all three request types without requiring a user interaction or creating a separate expiry message.

#### Scenario: Approval or manual action expires
- **WHEN** MCP announces that an approval or manual-action request has timed out
- **THEN** its original message retains the request text, has no inline buttons, and ends with the exact expiry notice
- **AND** no click is needed to trigger the update

#### Scenario: Question expires
- **WHEN** MCP announces that a question request has timed out
- **THEN** its original message retains the request text and direct-reply instruction and ends with the exact expiry notice
- **AND** a later reply cannot complete the expired request

#### Scenario: Repeated expiry notification
- **WHEN** the same expiry notification is received again
- **THEN** the notice appears only once and no new Telegram message or active request is created

#### Scenario: Unauthorized or malformed expiry notification
- **WHEN** the expiry endpoint receives missing or incorrect internal credentials or an invalid payload
- **THEN** it rejects the call without editing a Telegram message

#### Scenario: Telegram message editing fails
- **WHEN** Telegram rejects or times out the expiry edit
- **THEN** the failure is surfaced to MCP and logged without credentials
- **AND** the request remains expired and cannot accept a late answer
