# Independent QA report

## Current timeout contract — reduce-mcp-timeout

The fixed response wait is 850 seconds after successful delivery, with separate 10-second delivery and expiry-notification budgets. Configure the Codex HITL entry with `tool_timeout_sec = 900`. Expiry notification now edits the original Telegram message and removes buttons automatically. A prior live call returned `HITL_TIMEOUT` after 850.38 seconds of wall-clock elapsed time; it verified reduced timing only. The subsequent three-type live expiry check passed on 2026-10-12; the operator confirmed the real Telegram text and button updates. See `docs/LIVE_SMOKE.md` for the procedure and live record.

Current expiry verification (2026-10-12): `.venv/bin/python -m pytest tests --ignore=tests/test_e2e_docker.py -q` — **186 passed in 1.47s**; `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest tests/test_e2e_docker.py -q` — **1 passed in 4.72s**, against rebuilt MCP/bot images. Strict OpenSpec validation and diff checks passed. These runs verify the authenticated expiry route, original-message text/keyboard effects, concurrency, late answers, failure budgets, and existing regressions. Docker timing uses a mounted QA adapter asserting the production 850-second wait; no production timer is shortened. QA containers/network were cleaned up. The automated verification did not restart the user's running deployment. Subsequent live verification is recorded separately below. See `docs/VERIFICATION.md` for the complete record.

Initial timeout-only regression on 2026-10-11: **147 passed in 1.72s**. That result preceded the expiry refinement and is retained as earlier evidence.

### Live parallel expiry acceptance — 2026-10-12

Three agents each made one unanswered production MCP call, without retries or timer overrides:

| Type | Start (UTC) | End (UTC) | Wall-clock elapsed |
| --- | --- | --- | --- |
| approval | 05:02:52.211 | 05:17:02.988 | 850.777 seconds |
| question | 05:03:00.049 | 05:17:10.760 | 850.711 seconds |
| manual_action | 05:03:08.483 | 05:17:19.176 | 850.693 seconds |

All original invocations returned `{"status":"timeout","error_code":"HITL_TIMEOUT"}` with `isError: false`, before the 900-second client budget. Elapsed measurements use wall-clock time, not a monotonic clock. Read-only service logs for 05:02:45–05:17:35 UTC showed three expiry endpoint responses with HTTP 200 and no expiry-edit or notification failure entries.

The operator confirmed that all three original Telegram messages updated as expected: buttons were removed, the original text was retained, and the exact final paragraph `This request is no longer active. Your answer was not accepted.` appeared automatically. This visual result is operator confirmation, not direct assistant observation. The operator accepted the change for archive.

## Historical MVP record — former timeout contract

All sections below retain the archived `implement-hitl-mvp` evidence under its former 3550-second response wait and 3600-second client budget. Old task numbers, follow-up instructions, and acceptance exceptions describe that historical change and are superseded for current use by the instructions above. Original measurements and PASS results are preserved; the 961.926-second approval is not verification of the new timeout.

Date: 2026-10-11. Change: `implement-hitl-mvp`.

**PASS — automated implementation verification.** No blocking defect reproduced. External client/Telegram acceptance remains untested; this report does not certify completion of OpenSpec tasks 6.3 or 6.4.

## Executed evidence

| Check | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_integration_services.py -q` | 13 passed in 1.08s |
| `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest tests/test_e2e_docker.py -q` | 1 passed in 4.20s |
| `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest -q` | **147 passed in 5.49s; no skips** |

The full run includes 133 component/configuration/schema/skill/deployment/documented-contract tests, 13 new integration cases, and one container E2E case. Counts describe the run above, not a future guarantee.

## Passed coverage

- Actual MCP SDK discovery and call protocol; exactly three public input fields; invalid inputs fail before delivery.
- Both FastAPI applications connected through authenticated internal HTTP adapters and a Telegram HTTP double, with the actual bot lifespan and polling task. All three request types and five valid result statuses return through the original SDK call.
- Multiple waiting calls answered in reverse order; early answer before Telegram delivery returns; competing decisions accept exactly one answer; duplicates notify without reopening or removing buttons again.
- Unauthorized users and absent/wrong internal tokens have no completion effects; malformed result validation and structurally valid type mismatch preserve a waiting call.
- Authorized text replies to approval/manual requests are deleted and do not complete the request. Component tests additionally execute deletion failure, spoofed/malformed correlation, uncorrelated text, and non-text question inputs.
- Fixed 3550-second wait asserted via controlled timing; timeout returns `HITL_TIMEOUT`, cleans state, and rejects a late answer. Delivery failures clean the original SDK call. Component tests execute cancellation, restart-state loss, the 10-second delivery boundary, and shutdown cleanup.
- Telegram component tests execute polling recovery/offsets/single-poller shutdown, forwarding failures, malformed API responses, failed callback acknowledgment, notification failure, and failed keyboard edit after acceptance.
- Built MCP and bot images start as user `hitl` on an isolated Docker network. The bot uses a constructor URL seam via a test-only factory wrapper to reach a separate Telegram double. The real network SDK client discovers the tool and executes five concurrent calls, with answers queued in reverse message order through actual `getUpdates`; internal calls use service DNS names. All five results match their calls; repeated answers produce inactive notifications, and exactly four button keyboards are removed. Both internal endpoints reject missing tokens with 401. All containers remain running until cleanup.
- QA resources were removed in `finally`; subsequent `docker ps -a --filter name=hitl-qa` and `docker network ls --filter name=hitl-qa` returned no resources.

## Reproducing container checks

Install test dependencies and build both supplied Compose targets first. These placeholders are test values only:

```sh
python -m pip install -e '.[test]'
INTERNAL_API_TOKEN=qa-internal TELEGRAM_BOT_TOKEN=qa-bot TELEGRAM_CHAT_ID=42 TELEGRAM_ALLOWED_USER_ID=99 docker compose build
RUN_DOCKER_E2E=1 python -m pytest -q
```

The E2E test expects local image tags `codex-hitl-mcp:latest` and `codex-hitl-bot:latest` produced by Compose in this project directory. It binds random loopback ports and creates unique network/container names. It mounts `tests/support` read-only for the Telegram double and test-only bot factory. The third container is external test infrastructure, not an application deployment dependency. Production configuration and the response timeout are unchanged.

Without `RUN_DOCKER_E2E=1`, pytest explicitly skips the container test; such a run alone is not evidence of container verification. The recorded full run explicitly enabled it and had no skips.

## Security correction and repeated verification

Strict review reproduced a blocking DNS-rebinding exposure in the earlier build: an attacker-controlled Host/Origin could reach the public MCP tool. The MCP owner corrected transport security, restricting allowed hosts and origins to loopback addresses. QA changed only its SDK integration URL to the supported loopback address, then repeated the full suite after the Master rebuilt both images.

Final command: `RUN_DOCKER_E2E=1 .venv/bin/python -m pytest -q` — **147 passed in 5.49s, no skips**. This includes five malicious Host/Origin no-effect regression cases and three legitimate localhost/IPv4/IPv6 loopback acceptance cases. The container E2E additionally sends actual network requests with an attacker Host, attacker Origin, and deceptive loopback-prefix Origin, observes 421/403 rejection, and verifies no Telegram message was delivered before starting legitimate calls.

Rebuilt images used for final QA: MCP `7e2210220444`, bot `c9bdd6a92cdf` (local image ID prefixes). The earlier 139-test result describes the pre-review build; the final 147-test run supersedes it.

## Failed cases

The pre-correction DNS-rebinding defect was reported by strict review and fixed by its owner. No failures in the executed final suite. No production files or OpenSpec checkboxes were modified by QA.

## Untested external acceptance

- **Task 6.3:** Real Codex and Telegram smoke, real bot permissions, root/subagent interaction, and actual client network-disconnect behavior. Credentials were unavailable; the Master confirmed required environment variables and local `.env` were absent. Automated SDK/test-double results are not substitutes for these checks.
- **Task 6.4:** An actual 3550-second wait through the configured Codex client and return before its documented 3600-second call limit. The tests assert the production constant using controlled time, but do not measure live elapsed time or transport survival.
- Skill artifact/static scenario checks cannot prove agent reasoning behavior in a live task. Identity propagation is explicitly deferred by the approved design and current three-field contract.

Keep tasks 6.3 and 6.4 incomplete until their operator procedures have actual execution evidence. No specification exception or reduced timeout was used to obtain the automated PASS.
