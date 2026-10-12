# Repository Guidelines

## Project Structure & Module Organization

This repository contains specifications and plans; application code, tests, and Docker configuration are not implemented.

- `README.md`: agreed MVP contract and architecture.
- `docs/SKILL.md`, `docs/MCP_SERVER.md`, `docs/TELEGRAM_BOT.md`: component requirements.
- `openspec/config.yaml`: workflow context and artifact rules.
- `openspec/changes/implement-hitl-mvp/`: proposal, design, capability specs, and implementation checklist.
- `openspec/specs/`: main capability specifications; currently empty.
- `.agents/skills/`: OpenSpec workflow instructions.

Planned paths: `src/codex_hitl/` for application modules, `tests/` for tests, and `skills/hitl/SKILL.md` for the delivered skill. The configured `docs/project.md` is missing; use the component docs and report the gap.

## Build, Test, and Development Commands

- `openspec list --json`: list active changes and task progress.
- `openspec status --change implement-hitl-mvp`: inspect planning completion.
- `openspec validate implement-hitl-mvp --strict`: validate change artifacts.

No application build, test, or startup commands are available yet. Implementation should document its verified commands when adding Python packaging and Compose configuration.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions/modules, and `PascalCase` classes for planned Python code. Keep MCP and Telegram adapters separate. No formatter or linter is configured yet.

Use kebab-case OpenSpec change and capability names, such as `hitl-request-lifecycle`. Keep implementation decisions in `design.md` and testable behavior in capability specs.

## Testing Guidelines

The design selects pytest with async support; it is not installed or configured yet. Name tests `test_*.py`. Cover concurrent requests, first-response acceptance, timeout cleanup, authorization, and Telegram reply handling. Use mocked Telegram responses and controlled time without changing the production 850-second timeout. No coverage percentage is specified. Run relevant tests before marking implementation tasks complete; record live integration checks separately.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout. Follow the established Conventional Commits 1.0.0 convention: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, or `chore`. Example: `fix(mcp): reject duplicate answers`. Mark breaking changes with `!` or a `BREAKING CHANGE:` footer.

Before committing, run `git status`, inspect `git diff` and `git diff --staged`, and stage only one logical change. Use concise English descriptions. PRs should explain behavior, reference the relevant OpenSpec change or issue, and report validation and limitations.

## Security & Architecture Constraints

Keep credentials out of version control. Authenticate internal HTTP calls and restrict Telegram responses to the authorized user. Preserve the three-field tool schema, RAM-only request state, and two-service architecture. Planning workflows create artifacts only; begin implementation through an explicit apply request.

## Multi-Agent Development Workflow

For OpenSpec change `implement-hitl-mvp`:

1. Read all approved OpenSpec artifacts.

2. Before implementation, establish shared API
   contracts and assign non-overlapping file ownership.

3. Spawn `mcp_developer` and `telegram_developer`
   concurrently.

4. Wait for BOTH developers to finish.
   Do not start integration testing earlier.

5. Integrate shared configuration, Docker Compose,
   and Codex Skill components.

6. Spawn `tester`.
   Require successful integration and E2E tests.

7. If testing fails:
   - Assign defects to the responsible developer.
   - Wait for fixes.
   - Repeat the failed tests and affected regressions.

8. After testing passes, spawn `strict_reviewer`.

9. If review fails:
   - Assign findings to the responsible developer.
   - Wait for fixes.
   - Repeat testing.
   - Repeat the strict review.

10. Complete the workflow only when:
    - All required tasks are implemented.
    - Required tests pass.
    - No blocking review findings remain.

Only the Master may update OpenSpec tasks.md.
Do not archive the change automatically.
Do not weaken tests to obtain a PASS result.
