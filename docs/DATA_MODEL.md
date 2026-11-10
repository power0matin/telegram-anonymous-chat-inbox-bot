# Data model

**Status:** implemented as Alembic migration `0001` (`migrations/versions/0001_initial_schema.py`) and the SQLAlchemy models in `src/whisprlink/persistence/models/`. Application code that uses most of these tables arrives in later phases; the schema and its invariants are tested now (`tests/integration/`).

## Rules

PostgreSQL owns durable state; timestamps are `timestamptz` and UTC. Telegram IDs are internal routing data and never shown to participants. Link tokens are stored only as 32-byte hashes. Message bodies are never stored: content is relayed through Telegram server-side references. Enumerations are stored as `VARCHAR` guarded by named CHECK constraints (not native enum types), so values can evolve without `ALTER TYPE`. Every constraint and index has an explicit name.

## Tables (17)

| Table | Purpose |
| --- | --- |
| `users` | Internal ID, unique Telegram user ID, status (`active`, `restricted`, `banned`, `deleted`), timestamps. |
| `user_consents` | Versioned acceptance of rules and 18+ self-attestation; unique per user/type/version. |
| `user_preferences` | Language, random-chat and notification switches; contact and location sharing default to off. |
| `inbox_links` | Owner, 32-byte token hash, status (`active`, `paused`, `disabled`, `rotated`). |
| `inbox_threads` | One owner, one sender, link used, state (`pending`, `open`, `closed`), lifecycle timestamps, opaque `public_id`. |
| `inbox_messages` | Chronological timeline entry: sender role, optional same-thread reply target, type, media-group ID, Telegram source references, delivery state. |
| `message_media_items` | Ordered Telegram file references per message (album items). |
| `message_delivery_attempts` | Each delivery attempt and its outcome (`pending`, `delivered`, `failed_transient`, `failed_permanent`, `ambiguous`). |
| `inbox_open_events` | Application-level open receipt, tied to a delivered attempt of the same message. |
| `random_chat_sessions` | State (`searching`, `active`, `closed`), timestamps, end reason, opaque `public_id`. |
| `random_chat_participants` | Membership with slot 1 or 2, join/leave timestamps and reason. |
| `blocks` | Blocker, blocked, scope (`inbox`, `random_chat`). |
| `reports` | Reporter, reported, optional thread/message/session, category, status, resolution. |
| `moderation_actions` | Restrict/unrestrict/ban/unban by an admin Telegram ID. |
| `outbox_events` | Durable side-effect requests with idempotency key, state, attempts, lease. |
| `telegram_update_receipts` | `update_id` primary key for duplicate-update detection. |
| `admin_audit_logs` | Append-only record of privileged actions. |

## Invariants and how they are enforced

| Invariant | Mechanism |
| --- | --- |
| Telegram user ID is unique | `uq_users_telegram_user_id` |
| Link token hash is unique, fixed length | unique index + `octet_length = 32` CHECK |
| One live (`active`/`paused`) link per owner | partial unique index; rotating frees the slot |
| Thread has one owner and one different sender | NOT NULL FKs + `owner_id <> sender_id` CHECK; composite FK ties the link to its owner |
| Disabled, paused or rotated link cannot create a thread | trigger on `inbox_threads` (takes `FOR SHARE` on the link, so a concurrent rotation waits for an in-flight insert) |
| Every message belongs to a thread; reply target is in the same thread | FK + composite FK `(thread_id, reply_to_message_id)` |
| Only the two participants can access a thread | messages store `sender_role`, not a user ID, so no third party can be recorded; open events must be by the recipient (trigger) |
| Blocked pairs cannot create threads or new messages | triggers on `inbox_threads` and `inbox_messages`, in either direction |
| Closed threads accept no messages; owner cannot reply before opening | trigger on `inbox_messages` |
| Open receipt requires successful delivery of that message | composite FK to `message_delivery_attempts (id, message_id, outcome)` with `outcome = 'delivered'` CHECK and `ON UPDATE RESTRICT` |
| One open receipt per message | unique `message_id` |
| One active random membership per user | partial unique index on `user_id WHERE left_at IS NULL` |
| At most two distinct participants per session | `slot IN (1, 2)` CHECK + unique `(session_id, slot)` and `(session_id, user_id)` |
| Closing a session releases both participants | trigger on `random_chat_sessions` |
| Blocked, restricted, banned or deleted users cannot join a session | trigger on `random_chat_participants` |
| One Telegram update/message cannot create duplicate records | `telegram_update_receipts` PK; unique `(source_chat_id, source_message_id)` on messages and media items |
| Outbox events are idempotent; processing events hold a lease | unique `idempotency_key`; CHECK `processing_requires_lease` |
| Audit log cannot be edited | trigger rejects `UPDATE` (retention may still `DELETE`) |

## Design decisions

- **Block semantics:** a block in either direction stops new threads and new messages between the two users within its scope. Blocks are also checked at delivery time by the delivery worker (later phase); the database trigger is the last line of defence.
- **Account deletion:** the user row is tombstoned (`status = 'deleted'`, `telegram_user_id` cleared, `deleted_at` set). This keeps foreign keys valid without retaining the identifier, and lets the same Telegram account register again as a new user. Enforced by CHECK constraints.
- **Link lifecycle:** the link gates only the creation of *new* threads. Existing threads continue after rotation or disabling (the thread references the link it was created through). This policy is enforced by the schema; the user-facing flow is implemented in Phase 3.
- **Known limit:** a block committed concurrently with a thread or message insert is not serialized by the trigger (blocks are not locked). Delivery-time checks cover that window.

## Index direction

Implemented indexes follow the query shapes planned for later phases: threads by owner/state/activity and sender/state/activity, messages by thread/time/ID, sessions by state/time, outbox pending by next attempt and processing by lease expiry, reports by status/time, audit by time and admin. Validate with real queries and `EXPLAIN ANALYZE` as the features land.
