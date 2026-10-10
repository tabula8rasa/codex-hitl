# Spec Delta

## Purpose

Define how Codex and its subagents request necessary user involvement and safely resume or stop blocked work after a HITL result.

## ADDED Requirements

### Requirement: Escalate only blocking user involvement
The `hitl` skill SHALL instruct agents to invoke `hitl.request` only when continuing requires a user decision, authorization, or manual action that the agent cannot resolve independently within its requirements and authority.

#### Scenario: User involvement is necessary
- **WHEN** an agent cannot continue without user authorization
- **THEN** it requests an approval with a short title and a description of the context and required decision

#### Scenario: Agent can resolve the issue
- **WHEN** the agent can resolve an issue within its requirements and authority
- **THEN** it continues without invoking HITL

### Requirement: Use the three-field tool contract
The skill SHALL instruct agents to pass exactly `type`, `title`, and `description`, using `approval`, `question`, or `manual_action` as the type, and to wait for the tool result without managing identifiers or Telegram delivery.

#### Scenario: Ask a blocking question
- **WHEN** an agent needs information only the user can supply
- **THEN** it calls `hitl.request` with `type: question`, a title, and the specific question in the description
- **AND** it waits for the result of that call

### Requirement: Honor the returned decision
The skill SHALL instruct agents to act according to the returned status and SHALL prohibit treating rejection as authorization or an unconfirmed manual action as completed.

#### Scenario: Approval is rejected
- **WHEN** the result is `rejected`
- **THEN** the agent does not perform the action requiring that approval

#### Scenario: Manual action cannot be completed
- **WHEN** the result is `unable`
- **THEN** the agent does not continue as though the manual action succeeded

#### Scenario: Question is answered
- **WHEN** the result is `answered` with an answer
- **THEN** the agent uses that answer to continue the blocked task

### Requirement: Report timeout or unavailable tool without retry
On `HITL_TIMEOUT` or tool unavailability, the skill SHALL instruct agents to stop blocked work and report to their parent agent, or to the user when there is no parent. It SHALL prohibit automatic request retries.

#### Scenario: Subagent times out
- **WHEN** a subagent receives `HITL_TIMEOUT`
- **THEN** it stops the blocked work and reports the error to its parent without retrying

#### Scenario: Root agent cannot access the tool
- **WHEN** an agent without a parent finds the HITL tool unavailable
- **THEN** it stops the blocked work and informs the user without retrying
