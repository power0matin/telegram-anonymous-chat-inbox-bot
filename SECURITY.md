# Security policy

## Project status
WhisprLink is pre-alpha and is not ready for production use. Documented controls are requirements, not proof of an audited implementation.

## Reporting a vulnerability
Do not disclose exploitable vulnerabilities in public Issues or pull requests. Use GitHub's **Report a vulnerability** flow in the repository Security tab when available. Include impact, affected commit/version/path, safe reproduction steps, and suggested mitigation. Never include real tokens, personal data, or private message content.

If private reporting is unavailable, contact the repository owner through the contact information on the GitHub profile and request a private channel.

## Response
The maintainer will acknowledge reports as soon as practical, investigate impact, and coordinate a fix and disclosure timeline. No fixed response SLA is promised.

## Supported versions
There are no production releases yet. Supported versions will be documented after releases exist.

## Deployment
Until production security review is complete, do not use real user data or expose a development deployment publicly. Keep bot tokens and infrastructure credentials out of Git. Restrict database, Redis, logs, and backups.
