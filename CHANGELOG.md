# Changelog

Notable project changes are documented here.

The project has not published an executable release yet.

## Unreleased

### Added
- Application foundation (Phase 1): `InfrastructureSettings`/`Settings` with fail-closed production validation, structured JSON/console logging with secret and content redaction, async PostgreSQL engine lifecycle, Redis lifecycle with a bounded blocking pool and outage recovery, readiness and liveness checks (`python -m whisprlink healthcheck`), graceful shutdown on SIGINT/SIGTERM.
- Full database schema for the 17 agreed entities with Alembic migration `0001`, including database-enforced invariants (partial unique indexes, composite foreign keys, CHECK constraints, and integrity triggers).
- Unit tests and disposable PostgreSQL/Redis integration tests, `compose.test.yaml`, a locked dependency set (`uv.lock`), mypy type checking, and a CI workflow covering Python 3.12–3.14 with PostgreSQL and Redis services, migration checks, package build, and dependency audit.

### Changed
- `.env.example` documents every implemented setting; webhook-related placeholders were removed because webhook mode is not implemented.
- The start router is now created per dispatcher by `create_router()`.

### Earlier
- Established the WhisprLink brand and repository foundation.
- Introduced the WhisprLink visual identity: SVG icon and logo set, social preview, and brand guidelines.
- Added English and Persian project introductions.
- Added product, architecture, data model, security, roadmap, and development documentation.
- Added contribution, conduct, support, and vulnerability-reporting policies.
- Added the first executable aiogram scaffold with typed settings, polling startup, a minimal start handler, unit tests, and CI.
