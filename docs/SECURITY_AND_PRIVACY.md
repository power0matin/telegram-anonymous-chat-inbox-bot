# Security and privacy

**Status:** design requirements, not a security certification or implementation audit.

## Meaning of anonymous

WhisprLink aims to hide each participant's Telegram identity from the other participant inside the bot experience. It does **not** mean the operator or Telegram cannot identify/process accounts and messages, that messages are end-to-end encrypted, or that infrastructure operators cannot access stored data. Do not market the product as untraceable, fully anonymous, or end-to-end encrypted.

## Data minimization

- Store only identifiers and message references needed for routing and safety.
- Never log message text, captions, file contents, bot tokens, link tokens, or full callback payloads.
- Do not download media by default.
- Avoid collecting phone numbers, contacts, precise location, or date of birth.
- Define retention for unopened messages, closed threads, reports, deduplication records, and logs before public launch.
- Protect Telegram IDs, databases, backups, and operator access.

## Secrets

Read bot tokens, DB/Redis credentials, signing secrets, and webhook secrets from environment/secret management. Keep real .env out of Git. Use a distinct high-entropy secret for link tokens; rotate it by documented procedure. Fail closed when production secrets are missing/weak. Implemented: with `APP_ENV=production` the process refuses to start unless the bot token looks like a real token, `DEEP_LINK_SECRET` is present, at least 32 characters, not a placeholder and different from the token, at least one admin ID is configured, and the database URL has no placeholder password. Configuration errors name the offending setting but never echo its value. Logs run through a redaction processor that masks secret-like keys, message text/captions, bot-token-shaped strings, and credentials embedded in URLs; SQL parameter logging is disabled. Never paste credentials into Issues, logs, screenshots, or support requests.

## Authorization

Every callback and message action is untrusted. Before opening, replying, closing, blocking, reporting, or changing a link: resolve the authenticated user, load the object from PostgreSQL, verify participant/action authorization, verify current state and block policy, apply a conditional transaction-safe transition, then emit side effects through an outbox after commit. Opaque callback IDs are not authorization.

## Abuse prevention

Rate-limit sender, target link, and global traffic. Support inbox pause/disable/rotation. Blocking must suppress queued delivery. Provide reports in inbox and random chat, least-privilege moderation, and audit trails. Do not expose reporter identity. Define escalation and evidence retention before public traffic.

## Media and delivery

Treat captions, filenames, file IDs, and metadata as untrusted. Avoid downloading/redistributing outside intended Telegram flow. Handle protected, deleted, inaccessible, oversized, and unsupported content safely. Contact/location need explicit opt-in.

Notification is not an opened message. Open requires explicit View action and successful delivery. Do not send a successful-open receipt on failure or unresolved timeout. Telegram calls can time out after remote acceptance; mitigate duplicates and record ambiguity.

## Operations

Use structured logs with correlation IDs and redaction. Restrict logs, database, backups, and report evidence. Encrypt backups and test restores. Document incident response, secret rotation, and deletion before production.

## Pre-launch checklist

- [ ] Threat model reviewed.
- [ ] Authorization tests cover every callback and thread action.
- [ ] Concurrent matching and duplicate updates tested.
- [ ] Blocked pending deliveries suppressed.
- [ ] Link tokens unguessable and rotatable.
- [ ] No secrets in source, logs, CI output, or artifacts.
- [ ] Retention/deletion implemented and documented.
- [ ] Report handling and operator access audited.
- [ ] Backups protected and restore-tested.
- [ ] Dependencies and images reviewed.
- [ ] Age, safety, and jurisdiction policy defined.
- [ ] No unsupported anonymity/encryption claims.
