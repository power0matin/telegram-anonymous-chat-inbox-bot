# Product specification

**Status:** Draft — pre-implementation.

## Goal

Build one maintainable Telegram bot with two complementary experiences: random one-to-one anonymous chat and personal anonymous inbox links. The inbox is not a one-way confession form: after opening an incoming message, both participants can exchange messages and media in one thread while their Telegram identities remain hidden from each other.

## First-release non-goals

Anonymous group rooms, calls, live streaming, a web inbox, end-to-end encryption claims, discovery by phone/username/contact list, monetization, and complex matching preferences.

## Roles

- **Inbox owner:** activates a link, receives submissions, and may reply, close, block, or report.
- **Sender:** opens a link, submits a message, receives replies, and may continue the thread.
- **Random-chat participant:** joins the waiting pool and is paired with one eligible user.
- **Operator:** handles service health and abuse reports with audited privileged access.

## Personal anonymous inbox

- A user must start the bot before notifications can be sent.
- Each owner receives a deep link with an opaque, unguessable token; it must not encode the owner's Telegram ID.
- Owner can pause, disable, or rotate the link. Disabled/rotated links cannot create new threads.
- Accept text and supported Telegram message types.
- Persist message/thread and an outbox event before notifying the owner. Notification says a message is waiting and excludes its content.
- Owner explicitly chooses **View message**. Record an open event only after successful content delivery.
- Notify sender only after successful delivery. This is an application-level receipt, not a Telegram read receipt.
- Duplicate Telegram updates and callback taps must not create duplicate logical messages or transitions.

### Threaded replies

Each initial submission creates one thread. The first owner reply activates bidirectional messaging. Replies share one chronological timeline and may reference any earlier message in that thread. Both participants may continue until closed, blocked, reported, or expired by policy. Only participants may access or reply.

### Media scope

Planned: text/entities, photo, video, voice, audio/music, document, sticker, animation/GIF, video note, and albums. Test each type against Bot API methods and source-message restrictions. Unsupported/protected content must fail clearly. Contact/location need separate opt-in decisions; polls and service messages are out of initial scope. Albums need special handling because media delivery and inline controls may require separate messages.

## Random one-to-one chat

Find a chat moves an eligible idle user to SEARCHING. A match creates one session with exactly two distinct participants. Messages relay only while active. Either user can skip, stop, block, or report.

A user can belong to at most one active search/chat session. Pair creation must be atomic; cancel/stop must be race-safe. Stale waiting sessions must recover after restarts. Matching excludes blocked, restricted, paused, and busy users. Start with simple random matching; defer preferences until concurrency and safety are proven.

## Safety and controls

Both experiences need per-user/global rate limits, block/report, clear rules, operator audit logs, and user-controlled inbox availability. Blocking must suppress queued deliveries. Reports must not expose reporter identity. Define retention, deletion, harmful-content handling, and age policy before public launch.

## Main menu

Primary: **Find a chat**, **My anonymous link / Inbox**. Secondary: profile/statistics, settings/privacy, help/rules.

## Domain states

Inbox thread: PENDING → NOTIFIED → OPENING → OPENED → ACTIVE → CLOSED. Exceptional states: BLOCKED, REPORTED, EXPIRED, DELIVERY_FAILED. Message delivery state should be modeled separately.

Random user: IDLE → SEARCHING → CHATTING → IDLE. RESTRICTED and PAUSED are eligibility flags.

Outbox: PENDING → PROCESSING → SENT, with bounded retryable/non-retryable failure states. Telegram timeouts can be ambiguous; do not promise exactly-once external delivery.

## Acceptance criteria

- Owner activates/shares a link; visitor submits text and supported media.
- Notification excludes content; explicit View delivers it; sender receipt follows only successful delivery.
- Owner replies anonymously; sender can reply in the same thread.
- Block, report, close, pause, invalid/disabled/rotated link behavior works.
- Duplicate updates/callbacks do not corrupt state.
- Concurrent users cannot be double-matched; stop/skip and restart recovery work.
- No bot-generated message exposes Telegram identity.
- Config is validated, migrations build cleanly, logs redact secrets/content.
- Tests cover state transitions, access control, concurrency, retries, and media.

## Decisions before implementation

Finalize retention, contact/location policy, minimum age and launch jurisdictions, owner reply controls, media retention/moderation model, and polling vs webhook deployment.
