# Verification record

## Current timeout contract — reduce-mcp-timeout

The fixed response wait is 850 seconds after successful delivery, with separate 10-second delivery and expiry-notification budgets. Configure the Codex HITL entry with `tool_timeout_sec = 900`. Expiry notification now edits the original Telegram message and removes buttons automatically. A prior live call returned `HITL_TIMEOUT` after 850.38 seconds of wall-clock elapsed time; it verified reduced timing only. The subsequent three-type live expiry check passed on 2026-10-12; the operator confirmed the real Telegram text and button updates. See `docs/LIVE_SMOKE.md` for the procedure and live record.

### Expiry refinement verification — 2026-10-12

| Check | Actual result |
| --- | --- |
| `INTERNAL_API_TOKEN=qa-internal TELEGRAM_BOT_TOKEN=qa-bot TELEGRAM_CHAT_ID=42 TELEGRAM_ALLOWED_USER_ID=99 docker compose build` | Both final images built successfully |
| `.venv/bin/python -m pytest tests --ignore=tests/test_e2e_docker.py -q` | **186 passed in 1.47s** |
| `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest tests/test_e2e_docker.py -q` | **1 passed in 4.72s** |
| `openspec validate reduce-mcp-timeout --strict` | Valid |
| `git diff --check` | Passed |

Final local image IDs: MCP `9a0cbf1211ae`, bot `304bf28ed995`. These results include strict expiry payload/response validation; endpoint authorization and configured-chat targeting; original-text preservation and exact suffix for approval/manual-action/question requests; repeated identical edits; safe Telegram, transport, invalid-response, and total-budget failures; cancellation propagation; inactivity before editing; concurrent message correlation; and no expiry editing after an accepted answer. The client budget test includes delivery, response, and expiry work (870 seconds total within 900).

The Docker test uses both rebuilt production images and actual network SDK/internal HTTP calls. Only the mounted QA MCP factory controls the wait through a protected test trigger, asserting the requested production wait is 850; neither the trigger nor timer override is shipped in production. The Telegram double records actual text/keyboard effects for three concurrent expirations. All original roundtrip, authentication, Host/Origin, duplicate-response, non-root-container, and cleanup checks remain. There were 187 passing tests across the two final runs; no skips in either run. No `hitl-qa` containers or networks remained after cleanup. The build did not restart the user's running deployment, and no new live Telegram message was sent during this implementation.

### Live parallel expiry acceptance — 2026-10-12

Three agents each made one unanswered production MCP call, without retries or timer overrides:

| Type | Start (UTC) | End (UTC) | Wall-clock elapsed |
| --- | --- | --- | --- |
| approval | 05:02:52.211 | 05:17:02.988 | 850.777 seconds |
| question | 05:03:00.049 | 05:17:10.760 | 850.711 seconds |
| manual_action | 05:03:08.483 | 05:17:19.176 | 850.693 seconds |

All original invocations returned `{"status":"timeout","error_code":"HITL_TIMEOUT"}` with `isError: false`, before the 900-second client budget. Elapsed measurements use wall-clock time, not a monotonic clock. Read-only service logs for 05:02:45–05:17:35 UTC showed three expiry endpoint responses with HTTP 200 and no expiry-edit or notification failure entries.

The operator confirmed that all three original Telegram messages updated as expected: buttons were removed, the original text was retained, and the exact final paragraph `This request is no longer active. Your answer was not accepted.` appeared automatically. This visual result is operator confirmation, not direct assistant observation. The operator accepted the change for archive.

### Initial timeout-only verification — 2026-10-11

Executed on 2026-10-11 using the existing repository virtual environment (system Python has no pytest):

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_mcp_lifecycle.py tests/test_integration_services.py -q` | 31 passed in 1.39s |
| `.venv/bin/python -m pytest tests/test_documented_contracts.py -q` | 2 passed in 0.82s |
| `.venv/bin/python -m pytest tests --ignore=tests/test_e2e_docker.py -q` | 147 passed in 1.72s |
| `openspec validate reduce-mcp-timeout --strict` | Valid |
| `git diff --check` | Passed |

Controlled-time tests assert the production 850-second response wait, unchanged timeout result, cleanup, and late-answer rejection. The parsed README configuration and alternate registration instructions specify 900 seconds; delivery plus response waiting fits within that budget. At that initial verification stage Docker E2E and real elapsed-time timeout measurement had not been run. The expiry verification and subsequent live timing observation above supersede that limitation; historical MVP evidence below remains unchanged.

### Timeout reference audit

Reviewed hidden and tracked project files using `rg -n --hidden -g '!.git' -g '!.env' '3600|3550|3_600|3_550|tool_timeout_sec|RESPONSE_WAIT_SECONDS|59 minutes|hour' .`, plus alternative duration spellings. Current runtime, test assertions, client examples, and operational instructions use 850/900 seconds. Independent delivery and Telegram polling timeouts remain unchanged.

Remaining former values are confined to the archived MVP artifacts, the explicitly labeled historical records in `docs/LIVE_SMOKE.md`, `docs/TEST_REPORT.md`, and this file, and old-to-new context/rollback explanations in the archived reduce-mcp-timeout artifacts. All three delta specs were synced to the main specs before archiving the completed change on 2026-10-12. Verified the original report bodies and recorded measurements were retained verbatim.

## Historical MVP record — former timeout contract

All sections below retain the archived `implement-hitl-mvp` evidence under its former 3550-second response wait and 3600-second client budget. Old task numbers, follow-up instructions, and acceptance exceptions describe that historical change and are superseded for current use by the instructions above. Original measurements and PASS results are preserved; the 961.926-second approval is not verification of the new timeout.

Date: 2026-10-11. Change: `implement-hitl-mvp`. This record distinguishes automated evidence from live operator checks.

## Skill scenario review

Reviewed `skills/hitl/SKILL.md` against the approved agent capability:

| Scenario | Required instruction | Review |
| --- | --- | --- |
| Authorization is blocking | Invoke approval with context and specific decision | Present |
| Issue can be resolved within authority | Continue independently | Present |
| Blocking question/manual action | Exactly type, title, description and wait | Present |
| Approval rejected | Do not treat rejection as authorization | Present |
| Manual action unconfirmed | Do not treat it as completed | Present |
| Subagent timeout or unavailable tool | Stop blocked work, report to parent | Present |
| Root timeout or unavailable tool | Inform user | Present |
| Failure | No automatic retry | Present |

Static tests and the bundled skill validator validate the delivered artifact; they do not establish actual model reasoning behavior. Live agent exercises are separate.

## Preparation evidence

- Clean `.venv` created using Python 3.14.7; dependencies installed and editable package built successfully.
- Shared contract/config/auth tests: 43 passed.
- Shared plus skill/deployment artifact checks: 46 passed.
- Skill validator: `Skill is valid!`.
- Installed Codex CLI: 0.162.1; `codex mcp add --help` confirms HTTP `--url` registration. Operator timeout configuration follows official [MCP documentation](https://developers.openai.com/codex/mcp) and [configuration reference](https://developers.openai.com/codex/config-reference).
- `docs/project.md` is absent; followed AGENTS.md fallback to component docs and README. Historical design statements about no Git repository are stale; this checkout has `.git`.

## External checks

Real Telegram/Codex smoke and the live 3550-second wait are not yet executed. They require configured operator credentials and a client connected to this deployment. Accelerated automated timeouts are not substitutes. Tasks 6.3 and 6.4 must remain unchecked unless actual observations are recorded.

## Integrated implementation evidence

- MCP developer: 20 component/SDK tests passed; independently rerun by Master, 20 passed.
- Telegram developer: 55 component tests passed; compilation passed.
- Combined unit/SDK/shared/skill/deployment checks after integration: `.venv/bin/python -m pytest -q` → 124 passed in 0.86s.
- Separate clean installation in `/tmp/codex-hitl-clean-verify`: `pip install -r requirements.lock -e '.[test]'` succeeded; both application factories imported.
- Documented internal JSON message/answer examples validated against strict models.
- Compose configuration resolved successfully using fake test-only variables.
- `docker compose build` succeeded for both targets: `codex-hitl-mcp:latest` (`a4a966de53d9`) and `codex-hitl-bot:latest` (`1b497111b4e3`). Buildx was unavailable; Docker used its classic builder successfully.
- Independent integration/E2E testing and strict review are recorded below when completed.

## Independent QA and Master confirmation

- Independent tester reported automated **PASS**, with full evidence in `docs/TEST_REPORT.md`.
- `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest -q`: QA executed **139 passed in 5.36s, no skips**; Master independently reran **139 passed in 5.72s, no skips**.
- Includes 13 SDK/two-service/Telegram polling integration cases and one actual built-container network E2E case exercising five concurrent outcomes, reversed answers, duplicate rejection, authenticated internal connectivity, and non-root process startup.
- Test containers and their isolated network were cleaned up after both runs. No real Telegram messages were sent.
- `pip check`: no broken requirements. `git diff --check`: clean.
- Required Telegram/internal credential environment variables are absent; `.env` does not exist. Real operator smoke and the hour-long client budget check remain unexecuted. OpenSpec tasks 6.3 and 6.4 remain unchecked; progress is 22/24.

## Strict review, first pass and correction

The first strict review returned **FAIL** for one verified high-severity defect: the MCP SDK session manager default disabled DNS rebinding protection. Host/Origin values from an attacker-controlled domain reached `/mcp`, delivered a request, and returned its result despite loopback deployment. No browser exploit was run; the transport acceptance and effects were reproduced independently. No additional actionable findings were reported.

The MCP owner corrected this by explicitly enabling SDK transport security with loopback-only Host/Origin allowlists. Five negative transport cases now reject hostile Host or Origin values before delivery/pending effects; three positive cases preserve IPv4, localhost, and IPv6 loopback discovery. Component tests after correction: 28 passed. In-process integration SDK clients now use the same documented loopback endpoint. Images, independent QA, and strict review must be repeated before accepting this correction.

## Post-correction verification

- Both production images rebuilt successfully: MCP `7e2210220444`, bot `c9bdd6a92cdf` (local image IDs).
- Master independently reran corrected MCP tests: **28 passed in 0.57s**.
- Independent QA reran the complete suite against the rebuilt images: `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest -q` → **147 passed in 5.49s, no skips**.
- Actual container E2E now also rejects hostile Host/Origin and deceptive origin values with HTTP 421/403 and verifies no Telegram delivery. Legitimate loopback SDK clients and all five request outcomes still work. QA containers/network were removed.
- `git diff --check` and strict OpenSpec validation pass after correction. Final strict re-review follows separately.

## Final strict review and implementation status

Independent strict re-review: **PASS — no unresolved blocking implementation findings**. The reviewer independently reproduced hostile/deceptive Host/Origin rejection (HTTP 421/403), zero deliveries/pending effects, and successful original-call results for legitimate IPv4, localhost, and IPv6 clients. Reviewer regression execution: **28 MCP lifecycle/SDK tests passed in 0.64s**. No additional actionable findings remained after reinspection of lifecycle, authorization, Telegram handling, deployment, skill, and regressions. The reviewer modified no files.

Implementation and automated verification are complete. Overall OpenSpec acceptance is **22/24 verified tasks**, pending only live tasks **6.3 and 6.4**. No task was checked based on deferred or simulated live behavior. The actual response wait remains 3550 seconds. Follow `docs/LIVE_SMOKE.md` with operator credentials and a configured Codex connection to complete external acceptance. The change remains active and unarchived. No Git commit was requested or created.

## Port update

Operator requested MCP port 8100 and bot port 8101. Updated container listeners/exposed ports, Compose loopback mapping and internal service URLs, native startup/client examples, design/contracts, and affected tests. Both images rebuilt successfully with the new ports. Compose configuration validates; full enabled suite: `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest -q` → **147 passed in 5.48s**, including real container connectivity on the new listeners. Strict OpenSpec validation and `git diff --check` pass. Live acceptance tasks remain incomplete. The shareable `.env.example` was restored to blank credential values; local configuration remains in ignored `.env`.

## Subsequent live acceptance, 2026-10-11

Real Codex/Telegram calls now observed: root approval `approved`/`rejected` and manual action `completed`/`unable` all passed. Rejection and inability did not authorize or complete any real action. Concurrent question subagents returned distinct answers to their own calls in reverse completion order (Q2 `BRAVO`, then Q1 `THIS`); concurrent mixed-type subagents returned manual action `unable`, then approval `approved`. Exact results and elapsed measurements are in `docs/LIVE_SMOKE.md`.

Operator reports basic connection and input handling had already passed. Live unauthorized-user testing was deferred because no second account is available; duplicate testing has not been performed. These are not certified by this session.

An initial timeout attempt received `approved` after 63.361 seconds. The operator then selected a 15–20-minute connection-survival check: the same original MCP invocation returned `approved` after **961.926 seconds (16 minutes 1.926 seconds)**, without an error or retry. **Requested connection-survival check passed.** Neither attempt reached the server timeout; the actual `HITL_TIMEOUT` at 3550 seconds and return before the 3600-second client limit remain unverified. Elapsed measurements use wall time. Tasks 6.3/6.4 remain unchecked pending complete required live evidence. Production code and timeout were not changed.

## Operator archive acceptance, 2026-10-11

The operator explicitly confirmed: “Sync now. mark task 6.4 as approved, 6.3 as skipped”. The MVP is accepted for archive with task 6.3 skipped and task 6.4 approved by acceptance exception. This decision does not establish a full-duration timeout PASS: only 961.926 seconds of connection survival followed by `approved` was measured. Live duplicate/unauthorized-user checks and the actual 3550-second `HITL_TIMEOUT` remain unverified and deferred. Production timeout and behavior requirements remain unchanged.

Final archive checks: full automated suite including Docker E2E **147 passed in 7.50s**; dependency consistency and Compose configuration passed. All four main specs were synced with their Purpose and requirement blocks preserved and passed strict validation. The `spec-driven` change is archived at `openspec/changes/archive/2026-10-11-implement-hitl-mvp/`. Its final tracked count is 23/24: task 6.3 has a skipped marker, which the CLI counts as incomplete, and task 6.4 records the explicit acceptance exception. Earlier implementation-session status paragraphs above are historical; this archive decision supersedes their active-change status.
