# Spec Delta

## Purpose

Allow concurrent Codex calls to wait for independently correlated user responses and return a single final result to each original MCP invocation.

## ADDED Requirements

### Requirement: Expose the fixed MCP request tool
The MCP service SHALL expose `hitl.request` through `POST /mcp` with exactly three input fields: `type`, `title`, and `description`. It SHALL accept only `approval`, `question`, and `manual_action` request types and validate inputs before message delivery.

#### Scenario: Invalid request arguments
- **WHEN** a call supplies an unsupported request type or omits a required field
- **THEN** the call fails validation without creating an active request or delivering a Telegram message

#### Scenario: No identity inputs
- **WHEN** a client inspects the tool schema
- **THEN** it exposes only the three documented fields and does not require identifiers or agent identity

### Requirement: Correlate concurrent requests with their original calls
Each valid call SHALL receive a UUIDv4 request identifier, register an active request before sending it to the bot, and return its result through the original call. Concurrent requests SHALL remain independently addressable.

#### Scenario: Responses arrive out of order
- **WHEN** two calls are waiting and the second request is answered first
- **THEN** only the second call resolves with that answer
- **AND** the first remains pending until its own terminal outcome

#### Scenario: User answers during message delivery
- **WHEN** a valid answer arrives after registration but before the delivery response returns
- **THEN** the answer can complete that active request and is returned after successful delivery

### Requirement: Accept only responses matching the request type
The authenticated `POST /internal/answer` endpoint SHALL accept `request_id` and `answer`. Valid answers SHALL be `approved` or `rejected` for approval, `answered` with a text `answer` for question, and `completed` or `unable` for manual action. A type-mismatched answer SHALL receive `accepted: false` without completing the request.

#### Scenario: Type mismatch leaves request pending
- **WHEN** an active approval request receives an `answered` result
- **THEN** the endpoint returns `accepted: false` and the request continues waiting

#### Scenario: Valid answers preserve their result shapes
- **WHEN** an active request receives a valid result for its type
- **THEN** the endpoint returns `accepted: true`
- **AND** the original call returns the corresponding status, including the text answer for `answered`

### Requirement: Accept the first valid response exactly once
Only the first valid answer to an active request SHALL receive `accepted: true`. Duplicate, unknown, late, completed, or canceled request responses SHALL receive `accepted: false` and SHALL NOT reopen a request.

#### Scenario: Competing responses
- **WHEN** two valid responses compete for the same active request
- **THEN** exactly one receives `accepted: true` and determines the original call result
- **AND** the other receives `accepted: false`

#### Scenario: Response after termination
- **WHEN** an answer targets an unknown, timed-out, completed, or canceled request
- **THEN** the endpoint returns `accepted: false` without creating a request

### Requirement: Enforce the fixed wait timeout
The service SHALL wait at most 3550 seconds for a user response after successful message delivery. On timeout it SHALL return `{"status":"timeout","error_code":"HITL_TIMEOUT"}` through the original call and terminate the request.

#### Scenario: No response within the wait period
- **WHEN** the response wait reaches 3550 seconds without an accepted answer
- **THEN** the original call returns the documented timeout result
- **AND** a subsequent answer receives `accepted: false`

### Requirement: Clean up every terminal request
Active requests SHALL exist only in RAM and SHALL be removed on success, timeout, message-delivery failure, or cancellation of the call. Delivery failure SHALL terminate the call with an error. Restarting the service SHALL lose all pending requests.

#### Scenario: Bot delivery fails
- **WHEN** the message cannot be delivered to the bot successfully
- **THEN** the call terminates with an error and its active request is removed

#### Scenario: Call is canceled
- **WHEN** a waiting call is canceled
- **THEN** its active request is removed and cannot later be completed by the bot

#### Scenario: Service restarts
- **WHEN** the service restarts while requests are pending
- **THEN** those requests are not restored and subsequent answers to their identifiers receive `accepted: false`
