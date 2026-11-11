# Architecture

**Status:** proposed architecture; the foundation layer (configuration, logging, PostgreSQL schema/engine, Redis lifecycle, health, application lifecycle) is implemented. Everything else below is still a target.

## Shape

Use a **modular monolith**: one Python application and one deployment unit with explicit internal boundaries. Avoid premature microservices.

Telegram Bot API → aiogram adapter → application use cases → domain policies → PostgreSQL transaction + outbox → delivery worker → Telegram Bot API. Redis supports temporary coordination, rate limits, and cache; PostgreSQL remains authoritative.

## Technology direction

Python 3.12+, aiogram 3, PostgreSQL, SQLAlchemy 2 async, Alembic, Redis, Pydantic Settings, pytest, pytest-asyncio, Ruff, static type checking, and Docker Compose. Dependencies are resolved and locked in `uv.lock`; CI installs from it (`uv sync --frozen`).

## Module boundaries

| Module | Responsibility |
| --- | --- |
| telegram | aiogram routers, callbacks, message adapters, keyboards |
| application | use cases, orchestration, authorization |
| domain | entities, state transitions, invariants |
| inbox | links, submissions, threads, replies |
| matching | waiting pool and pair lifecycle |
| moderation | blocks, reports, restrictions |
| delivery | outbox, notifications, retry policy |
| persistence | models, repositories, transactions |
| config | validated settings |
| observability | logs, metrics, health |

Handlers stay thin: parse update, call use case, render response. Business transitions do not live only in callback handlers.

## Persistence and concurrency

PostgreSQL is the durable source of truth.

### Matching
- Enforce at most one active matching/chat membership per user with database constraints or an equivalent transactional invariant.
- Claim candidates inside a transaction using row locks or a safe equivalent.
- Re-check eligibility, blocks, and session state inside the transaction.
- Create session and both participant rows atomically.
- Serialize cancellation against matching.
- Recover stale SEARCHING records after restarts.

Redis may accelerate candidate discovery, but PostgreSQL validates and commits the pair. A queue pop alone does not prove availability.

### Inbox
- Persist thread/message and outbox event in one transaction.
- Worker sends owner notification after commit.
- Deduplicate Telegram updates using stable update/message identifiers.
- Every callback re-checks participant, thread state, and authorization.

### Open and delivery
- Explicit View claims pending delivery with a conditional transition.
- Send content outside a long DB transaction.
- Record opened event only after Telegram confirms successful delivery.
- For timeout ambiguity, retry carefully and preserve uncertainty.
- Notify sender only after opened transition commits.

## Transactional outbox

Commit domain state and outbox event together. Worker claims event, calls Telegram, records result and attempts, then retries transient failures with bounded backoff. Do not hold DB locks during network calls. Use stable event IDs and idempotency keys. Exactly-once external delivery cannot be guaranteed across every timeout boundary.

## Telegram adapter

- Callback payloads are compact and opaque; never put raw IDs, secrets, or authorization decisions in them.
- Treat callbacks as untrusted and authorize server-side.
- Store source chat/message references needed for delivery; do not download media by default.
- Test every supported media method and source-message restriction.
- Handle albums separately where group delivery and controls require different messages.
- Handle deleted, protected, inaccessible, and unsupported content.
- Use Telegram numeric user ID internally, never username as primary key.

## Redis

Use for rate-limit counters, cache, temporary worker coordination, and short-lived deduplication hints backed by DB constraints. Never make it the only store for sessions, threads, blocks, reports, or receipts.

## Reliability and tests

Graceful shutdown; recover expired worker leases; explicit migrations; readiness vs liveness checks; structured redacted logs. Test state machines, authorization, DB constraints, concurrent matching, outbox, media adapters, duplicate updates, callback replay, network timeout, cancellation/match race, concurrent opens, and blocked queued deliveries. Tests use disposable infrastructure only.

## Implemented foundation (Phase 1)

- `whisprlink.config`: `InfrastructureSettings` (database, Redis, timeouts; needs no Telegram token, so Alembic and the health check can run without one) and `Settings` (adds Telegram, admin and secret settings, with fail-closed production validation).
- `whisprlink.persistence`: `Database` owns the async engine (pre-ping, bounded pool, UTC session time zone, `idle_in_transaction_session_timeout` so a transaction cannot sit open while waiting on a network call) and the SQLAlchemy models for the agreed entities.
- `whisprlink.infrastructure.redis`: `RedisManager` with a blocking, bounded connection pool, retry with backoff, and reconnection after outages.
- `whisprlink.observability`: readiness report (PostgreSQL required, Redis degrades) and an event-loop heartbeat file for liveness. `python -m whisprlink healthcheck [--liveness]` exposes both.
- `whisprlink.app`: `Application` starts dependencies with bounded retries, runs polling, and shuts down on SIGINT/SIGTERM in reverse dependency order.
