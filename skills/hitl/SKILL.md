---
name: hitl
description: Use when continuing a task requires a decision, authorization, or manual action from the user.
---

# HITL

## When to Invoke

Call `hitl.request` only when you cannot continue the task without user involvement. Do not escalate questions to the user if you can resolve them independently within the requirements and your authority.

## Arguments

Pass exactly three fields:
- `type`: `approval` | `question` | `manual_action`;
- `title`: a short title;
- `description`: context and the specific action or question.

## After Invocation

Wait for the result and act accordingly. Do not treat a rejection as authorization; do not treat an unconfirmed manual action as completed.

Use an `answered` result's text to continue the blocked task. Continue an approved action only on `approved`, and a required manual action only on `completed`. On `rejected` or `unable`, stop the dependent action and report the outcome. Identifiers, Telegram delivery, and waiting mechanics are managed by the tool; do not add fields to manage them.

On `HITL_TIMEOUT` or if the tool is unavailable, stop the blocked work and report the error to the parent agent. If there is no parent agent, inform the user. Do not automatically retry the request.
