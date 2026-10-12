# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
