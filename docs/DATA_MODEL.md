# Data model

**Status:** conceptual; refine with actual query and transaction design.

## Rules

PostgreSQL owns durable state; timestamps are UTC. Telegram IDs are internal routing data and never shown to participants. Personal link tokens are high-entropy random values; store secure hashes where practical, never derive from Telegram IDs. Use opaque IDs, separate message delivery from thread lifecycle, and enforce idempotency with database constraints. Avoid storing message bodies or downloading media without a defined need.

## Proposed entities

- **users:** internal ID, unique Telegram user ID, account/safety status, timestamps, optional locale.
- **inbox_links:** owner ID, token hash, status, rotation/disable metadata, timestamps.
- **inbox_threads:** owner ID, sender ID, state, lifecycle timestamps, last activity. Access limited to participants.
- **inbox_messages:** thread ID, sender participant ID, optional same-thread reply target, Telegram source chat/message references, update deduplication key, type/media-group metadata, timestamp, delivery state.
- **inbox_open_events:** message/thread, opening actor, timestamp, delivery correlation ID; unique logical open event.
- **random_chat_sessions:** state, created/started/ended timestamps, end reason.
- **random_chat_participants:** session/user IDs, state, joined/left timestamps; unique active membership per user.
- **blocks:** blocker, blocked, scope, timestamp; unique pair/scope.
- **reports:** reporter/reported IDs, optional thread/session, category, explanation, state, timestamps; audited operator review.
- **outbox_events:** event type, aggregate, minimal payload, idempotency key, state, attempts, retry/lease metadata.
- **telegram_update_receipts:** unique update ID and processing result, with retention policy.

## Database invariants

1. User has at most one active random-chat membership.
2. A random session has no more than two participants.
3. Thread has exactly one owner and one sender participant.
4. Every message belongs to one thread.
5. Reply target belongs to the same thread.
6. Only participants can access a thread.
7. Open receipt references successful content delivery.
8. Blocked direction cannot create/deliver new messages.
9. Disabled/rotated link cannot create a new thread.
10. One Telegram update cannot create duplicate logical records.

Enforce concurrency-critical invariants in the database, not only application validation.

## Index direction

Unique users.telegram_user_id; unique inbox_links.token_hash; inbox_threads by owner/state/activity and sender/state/activity; inbox_messages by thread/time/ID and unique update ID; sessions by state/time; participant active membership; blocks by blocker/blocked/scope; outbox by state/next_attempt/created. Validate with actual queries and EXPLAIN ANALYZE.
