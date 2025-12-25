# Repository Guidelines

## Project Structure & Module Organization
- `src/agent/` holds the Python package; entry points live in `src/agent/main.py` and
  `src/agent/auth_google.py`.
- `src/agent/nodes/` contains the LangGraph node implementations for the workflow.
- `tests/` contains pytest suites (typically `test_*.py`).
- `data/` stores runtime state like `agent_state.db` and OAuth tokens such as
  `google_token.json` (keep these out of commits).
- Top-level runtime artifacts: `Dockerfile`, `docker-compose.yml`, `.env.example`.

## Build, Test, and Development Commands
- `docker compose up -d` starts the agent container; `docker compose logs -f agent` tails logs.
- `python -m pip install -e '.[dev]'` installs dev dependencies for local runs.
- `ruff check .` runs lint checks; `ruff format --check .` verifies formatting.
- `pytest` runs the test suite from `tests/`.
- `mypy src` runs static type checks against `src/`.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation.
- Ruff enforces `line-length = 100` and formatting with `quote-style = preserve`.
- Type checking is strict (`disallow_untyped_defs`, `check_untyped_defs`), so add type hints.
- Naming: `snake_case` for functions/vars, `CapWords` for classes, `test_*.py` for test files.

## Testing Guidelines
- Framework: `pytest` with test discovery under `tests/`.
- Keep unit tests near the behavior they cover; prefer focused tests for node logic in
  `src/agent/nodes/`.
- Run all tests with `pytest`; run specific files with `pytest tests/test_email_parse.py`.

## Commit & Pull Request Guidelines
- Git history is unavailable in this workspace, so no project-specific commit convention is
  observable. Use concise, imperative summaries (e.g., "Add IMAP folder prefix handling").
- PRs should include a clear description, the tests run (or reason not run), and any config
  changes to `.env.example`.
- Do not include secrets or runtime state (`.env`, `.secrets/`, `data/*.json`, `data/*.db`) in PRs.

## Configuration & Security Tips
- Required settings are documented in `README.md`; prefer `.env` or Docker secrets.
- For Google OAuth, keep client secrets outside the repo (e.g., `./secrets/` or host paths).
