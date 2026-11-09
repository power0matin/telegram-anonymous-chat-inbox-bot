# Roadmap

A milestone is complete only when its acceptance criteria and tests pass.

## M0 — Product and repository foundation
- [x] Establish WhisprLink identity and repository structure.
- [x] Document product behavior, MVP boundaries, architecture, data model, and security.
- [ ] Finalize age policy, retention periods, and deployment mode.

## M1 — Application foundation
- [ ] Validated settings and structured logging.
- [ ] aiogram entry point and router structure.
- [ ] PostgreSQL lifecycle, SQLAlchemy models, Alembic migrations.
- [ ] Disposable test database workflow.
- [ ] Redis lifecycle and rate-limit abstraction.
- [ ] Health checks and graceful shutdown.
- [ ] Unit/integration tests and CI baseline.

**Exit:** application starts with validated config, clean migrations run, tests need no production services, logs redact secrets and user content.

## M2 — Personal inbox vertical slice
- [ ] User registration and personal deep links.
- [ ] Opaque token validation and pause/disable/rotation.
- [ ] Text submission and durable inbox records.
- [ ] Transactional notification outbox.
- [ ] Explicit View and application-level open receipt.
- [ ] Threaded replies, block, report, and close.
- [ ] Duplicate update, callback authorization, and delivery-failure tests.

**Exit:** complete text-only inbox conversation works end-to-end with privacy and authorization tests.

## M3 — Media and inbox hardening
- [ ] Photo, video, voice, audio, document, sticker, animation, video-note adapters.
- [ ] Album handling.
- [ ] Deleted/protected/inaccessible/unsupported content handling.
- [ ] Bounded retries and ambiguous-send handling.
- [ ] Retention/deletion implementation.
- [ ] Abuse limits and report review workflow.

## M4 — Random one-to-one matching
- [ ] Durable waiting state and atomic pair creation.
- [ ] Cancellation, stop, and skip.
- [ ] Two-way relay.
- [ ] One active session per user.
- [ ] Block/restriction exclusions.
- [ ] Stale-session recovery and restart tests.
- [ ] Competing match concurrency tests.

## M5 — Release readiness
- [ ] Load/failure tests.
- [ ] Moderation and incident runbooks.
- [ ] Retention, age, jurisdiction review.
- [ ] Production Docker images and deployment docs.
- [ ] Dependency/container scanning.
- [ ] Dashboards and backup/restore procedure.
- [ ] Tagged release after real acceptance testing.

Later ideas: language-aware matching, conversation prompts, referral analytics, profile controls, more locales, optional monetization after safety/reliability.
