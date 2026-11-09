# Contributing to WhisprLink

WhisprLink is pre-alpha; product and architecture feedback is as useful as code.

## Before contributing
- Read README.md and docs/PRODUCT_SPEC.md.
- Check the roadmap and existing Issues.
- Discuss major features or architecture changes before implementation.
- Never submit real credentials, private conversations, or personal data.

## Principles
- Keep changes focused and maintainable.
- Preserve the modular-monolith direction unless evidence justifies a change.
- Treat PostgreSQL as durable source of truth.
- Do not rely on process-local state for sessions or authorization.
- Add tests for state transitions and concurrency.
- Document migration, operational, and privacy implications.
- Do not claim end-to-end encryption or absolute anonymity.

## Workflow
1. Fork and create a focused branch from main.
2. Make the smallest coherent change.
3. Add/update tests and documentation.
4. Run checks described in docs/DEVELOPMENT.md.
5. Open a PR using the repository template.

Suggested prefixes: feat/, fix/, docs/, test/, refactor/, chore/.

## Commits
Conventional Commits are encouraged: feat: add inbox link rotation; fix: prevent duplicate match assignment; docs: clarify message-open semantics.

## Pull requests
Explain what changed, why, how it was tested, migration impact, Telegram/media behavior changes, privacy/moderation impact, and known limitations. Avoid unrelated refactors.

## Security
Do not open a public Issue for a suspected vulnerability. Follow SECURITY.md.

## Code of conduct
Participation is governed by CODE_OF_CONDUCT.md.
