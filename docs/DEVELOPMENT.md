# Development guide

**Current state:** the application foundation is implemented: validated settings, structured logging, PostgreSQL schema and migrations, Redis lifecycle, health checks, graceful shutdown, and a /start handler. Inbox, random chat, and delivery workflows are not implemented.

## Local environment

- Python 3.12 or newer (CI covers 3.12, 3.13, and 3.14).
- [uv](https://docs.astral.sh/uv/) for locked, reproducible installs.
- PostgreSQL 16 and Redis 7 (disposable instances for tests, see below).
- A Telegram bot token from BotFather for local smoke tests.

## Setup

```bash
uv sync --frozen --extra dev
cp .env.example .env   # then set TELEGRAM_BOT_TOKEN, DATABASE_URL, REDIS_URL
uv run alembic upgrade head
uv run python -m whisprlink
```

`uv sync` reads `uv.lock`. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the result; CI fails if the lock is stale. Without uv, `python -m pip install -e ".[dev]"` also works but is not reproducible.

Never put a real token in Git, issue reports, screenshots, or CI logs.

## Commands

| Command | Purpose |
| --- | --- |
| `python -m whisprlink` / `whisprlink run` | Start the bot (long polling). |
| `whisprlink healthcheck` | Probe PostgreSQL and Redis. Exit 0 only when both are healthy; prints JSON (`ok`, `degraded`, `unavailable`). Needs no Telegram token. |
| `whisprlink healthcheck --liveness` | Check the running process's heartbeat file. |
| `alembic upgrade head` / `alembic check` | Apply migrations / verify models and migrations agree. Reads `DATABASE_URL`. |

## Configuration

Settings come from environment variables and, when present, `.env`; names map to the uppercase keys in `.env.example`, which documents every setting. `InfrastructureSettings` (database, Redis, timeouts) needs no Telegram token; `Settings` adds the token, admin IDs, and `DEEP_LINK_SECRET`. With `APP_ENV=production` startup fails unless the token looks real, `DEEP_LINK_SECRET` is a non-placeholder of at least 32 characters, at least one admin ID is set, and the database URL has no placeholder password. Invalid configuration exits with code 2 and names the setting without printing its value.

Only `BOT_MODE=polling` is supported; webhook mode is rejected. `DATA_RETENTION_DAYS` is reserved and triggers no deletion yet.

Startup waits for PostgreSQL and Redis with bounded retries (`STARTUP_RETRY_ATTEMPTS`, `STARTUP_RETRY_DELAY_SECONDS`) and then exits non-zero if either is unreachable. After startup a temporary outage surfaces as per-call errors; the connection pools recover when the service returns.

## Tests

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=whisprlink --cov-report=term-missing
```

Unit tests need no services. Integration tests (marked `integration`) need a disposable PostgreSQL server and Redis:

```bash
docker compose -f compose.test.yaml up -d --wait
export TEST_DATABASE_URL=postgresql+asyncpg://whisprlink:test-only@localhost:55432/postgres
export TEST_REDIS_URL=redis://localhost:56379/15
uv run pytest
docker compose -f compose.test.yaml down
```

`TEST_DATABASE_URL` is a server admin URL: each test session creates a uniquely named database, migrates it with the real Alembic migrations, and drops it afterwards. Redis tests use unique key prefixes. If the variables are unset the integration tests are skipped; set `REQUIRE_INTEGRATION=1` (CI does) to make that a failure instead.

GitHub Actions runs lint, format check, mypy, the full test suite against PostgreSQL and Redis service containers on Python 3.12, 3.13, and 3.14, applies migrations to an empty database and runs `alembic check`, then builds the package, verifies the lock file, audits runtime dependencies with pip-audit, and validates `compose.test.yaml`.

## Engineering conventions

- Keep Telegram handlers thin; put business rules in application/domain services.
- Use async I/O consistently at application boundaries.
- Keep PostgreSQL transactions short.
- Use database constraints for concurrency-sensitive invariants.
- Use Redis only for ephemeral coordination and acceleration.
- Route external side effects through a durable outbox.
- Use UTC for persisted timestamps.
- Validate Telegram updates and callback payloads.
- Keep message content and secrets out of logs.
- Test state transitions, authorization, concurrency, failure/retry paths, and media behavior.
- Prefer small, focused pull requests with tests and documentation.

## Before opening a pull request

1. Read CONTRIBUTING.md.
2. Confirm the change fits PRODUCT_SPEC.md.
3. Add or update tests.
4. Update architecture/data-model/security docs when a design boundary changes.
5. Run applicable checks locally.
6. Explain behavior changes, migration impact, and security/privacy implications.

Use dummy credentials and isolated databases for tests. If a secret is committed accidentally, revoke/rotate it immediately; deleting the commit is not sufficient.
