# Development guide

**Current state:** an executable Telegram bot scaffold is available. It validates environment settings, configures standard-library logging, starts aiogram in long-polling mode, and responds to the /start command. Inbox, random chat, persistence, and delivery workflows are not implemented.

## Target local environment

- Python 3.12 or newer.
- Git.
- A Telegram bot token from BotFather for local smoke tests.
- PostgreSQL and Redis will be introduced with the first persistence slice; the current scaffold does not connect to them.

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the project and development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy .env.example to .env and set TELEGRAM_BOT_TOKEN. Never put a real token in Git, issue reports, screenshots, or CI logs.

Run:

```bash
python -m whisprlink
```

The whisprlink console command is also installed by the editable package.

## Configuration

Settings are loaded from environment variables and, when present, .env. Field names map to the uppercase keys in .env.example. The Telegram token is required and represented as a secret value. The current runtime supports BOT_MODE=polling; webhook mode is rejected until webhook ingress and secret validation are implemented.

Database and Redis settings are part of the configuration contract, but no connections are opened in this scaffold. DATA_RETENTION_DAYS is reserved for a future retention implementation and does not currently trigger data deletion.

## Quality checks

```bash
ruff check .
ruff format --check .
pytest
```

GitHub Actions runs lint, formatting, and unit tests on Python 3.12 for pull requests and pushes to main.

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
