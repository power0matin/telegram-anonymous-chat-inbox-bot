<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/whisprlink-logo-dark.svg">
    <img src="assets/brand/whisprlink-logo-light.svg" alt="WhisprLink" width="340">
  </picture>
</h1>
<p align="center"><strong>Anonymous conversations, on your terms.</strong></p>
<p align="center">An open-source Telegram bot combining random one-to-one chat, personal anonymous inboxes, and threaded replies.</p>
<p align="center"><a href="README.fa.md">فارسی</a> · <a href="docs/PRODUCT_SPEC.md">Product spec</a> · <a href="docs/ARCHITECTURE.md">Architecture</a> · <a href="CONTRIBUTING.md">Contributing</a> · <a href="SECURITY.md">Security</a></p>

> **Status: Pre-alpha.** The repository contains the application foundation: validated settings, structured logging, PostgreSQL and Redis lifecycle management with health checks and graceful shutdown, the full database schema with its first Alembic migration, a polling entry point with a minimal /start handler, and unit/integration tests with CI. The anonymous inbox, random-chat matching, media delivery, moderation workflows, and deployment tooling have not been implemented.

## What is WhisprLink?

WhisprLink is planned as one Telegram bot with two complementary ways to start a conversation:

| Experience | Purpose |
| --- | --- |
| **Random anonymous chat** | Matches two available users for a private one-to-one conversation without exposing their Telegram identities to each other. |
| **Personal anonymous inbox** | Gives each user a shareable deep link. Visitors can send text or supported media without being shown the recipient's identity. |
| **Threaded anonymous replies** | Lets the inbox owner open a message, reply, and continue in one chronological thread. |

## Planned inbox experience

1. A user starts WhisprLink and activates a personal inbox link.
2. Someone opens that link and sends text or supported Telegram media.
3. The recipient gets a notification that a message is waiting; its content is not included.
4. The recipient explicitly chooses **View message**. The bot delivers the content and records an application-level open event after successful delivery.
5. The recipient can reply. The sender receives the anonymous reply and can continue the same thread.
6. Either side can block, report, or close the conversation.

The sender's “seen” notification means the recipient explicitly opened the message in WhisprLink. It is not a native Telegram read receipt.

## Planned random chat

A user chooses **Find a chat**, enters a waiting state, and is paired atomically with another eligible user. Messages are relayed without exposing Telegram IDs or usernames. Either participant can skip, stop, block, or report.

## Product principles

- **Identity separation:** participant Telegram IDs and usernames are never shown to the other participant by the bot.
- **Explicit opening:** inbox content is delivered only after the recipient asks to view it.
- **One thread, one timeline:** replies stay chronological and can reference earlier messages.
- **Media-aware:** text, photos, videos, voice, audio, documents, stickers, animations, video notes, and albums are planned, subject to Bot API constraints and tests.
- **Safety by default:** rate limits, block/report flows, abuse controls, and user-controlled inbox availability are core requirements.
- **Minimal data:** store only what is needed to route messages, enforce safety, and operate the service.

## Planned technology

Python + aiogram 3, async modular monolith, PostgreSQL + SQLAlchemy 2 + Alembic, Redis, Pydantic Settings, pytest, pytest-asyncio, Ruff, and Docker Compose. PostgreSQL is intended as the source of truth; Redis is for ephemeral coordination, caching, and rate limits.

## Documentation

- [Product specification](docs/PRODUCT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Security and privacy](docs/SECURITY_AND_PRIVACY.md)
- [Roadmap](docs/ROADMAP.md)
- [Brand guidelines](docs/BRAND_GUIDELINES.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [Support](SUPPORT.md)

## Development status

The current slice provides the infrastructure foundation (configuration, logging, PostgreSQL schema and migrations, Redis lifecycle, health checks, graceful shutdown) and a /start route that responds. Onboarding, inbox delivery, threaded replies, random matching, moderation, media support, and production deployment are still unimplemented. There is no production-ready bot. Do not commit a real token or user data.

## Privacy

“Anonymous” describes what participants can see through the bot. The bot operator and Telegram still process information required to deliver messages. This project does not claim end-to-end encryption or anonymity from the operator.

## License

MIT — see [LICENSE](LICENSE).
