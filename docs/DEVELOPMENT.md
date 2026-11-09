# Development guide

**Current state:** documentation and repository foundation only. The bot runtime does not exist yet.

## Target local environment

- Python 3.12 or newer.
- Docker Engine with Docker Compose plugin.
- Git.
- Telegram bot token for local development only.
- PostgreSQL and Redis through disposable local services once the first application slice is introduced.

## Configuration

The eventual application will use environment-based typed settings. .env.example is a placeholder contract, not a working configuration yet. Never commit .env.

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

## Planned quality gates

Ruff lint/format, static type checking, unit tests, PostgreSQL integration and migration checks, Redis integration where relevant, end-to-end bot flow tests using mocked Telegram API boundaries, and security/dependency checks.

CI will be added with the first executable code so every check validates real behavior rather than passing an empty placeholder pipeline.

## Before opening a pull request

1. Read CONTRIBUTING.md.
2. Confirm the change fits PRODUCT_SPEC.md.
3. Add or update tests.
4. Update architecture/data-model/security docs when a design boundary changes.
5. Run applicable checks locally.
6. Explain behavior changes, migration impact, and security/privacy implications.

Use dummy credentials and isolated databases for tests. If a secret is committed accidentally, revoke/rotate it immediately; deleting the commit is not sufficient.
