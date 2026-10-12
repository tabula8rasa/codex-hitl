# Spec Delta

## MODIFIED Requirements

### Requirement: Enforce the fixed wait timeout
The service SHALL wait at most 850 seconds for a user response after successful message delivery. On timeout it SHALL return `{"status":"timeout","error_code":"HITL_TIMEOUT"}` through the original call and terminate the request.

#### Scenario: No response within the wait period
- **WHEN** the response wait reaches 850 seconds without an accepted answer
- **THEN** the original call returns the documented timeout result
- **AND** a subsequent answer receives `accepted: false`

#### Scenario: Response before expiration
- **WHEN** a valid answer is accepted before the 850-second response wait expires
- **THEN** the original call returns that answer using its documented result shape
- **AND** the request is removed from active state

## ADDED Requirements

### Requirement: Notify the bot when the response wait expires
When the 850-second response wait expires, MCP SHALL make the request inactive and send an authenticated expiry notification identifying the delivered Telegram message and its original request content. Notification work SHALL have a total budget of 10 seconds. Failure SHALL NOT replace the original `HITL_TIMEOUT` result or prevent terminal cleanup, and SHALL be logged without credentials.

#### Scenario: Unanswered delivered request expires
- **WHEN** the response wait reaches 850 seconds without an accepted answer
- **THEN** the request becomes inactive before MCP sends the expiry notification
- **AND** the notification identifies that request's message and content without affecting another request
- **AND** the original call returns the documented timeout result

#### Scenario: Notification fails or exceeds its budget
- **WHEN** the bot is unavailable, reports an editing failure, or expiry notification work reaches its 10-second budget
- **THEN** MCP logs the failure and returns the documented timeout result
- **AND** no active request remains and a late answer receives `accepted: false`

#### Scenario: Accepted answer wins before timeout
- **WHEN** a valid answer completes the request before the response wait expires
- **THEN** the original call returns the accepted answer
- **AND** MCP does not send an expiry notification for that request

#### Scenario: Late answer during expiry notification
- **WHEN** an answer arrives while notification of an already-expired request is in progress
- **THEN** MCP returns `accepted: false` and does not reopen or approve that request
