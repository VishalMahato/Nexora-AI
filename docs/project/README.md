# Project Documentation Hub

## Purpose

This folder is the single source of truth for project handoff. It contains the
technical and product documentation needed for a new team to own, extend, and
operate the Nexora system without relying on tribal knowledge.

If you are new to the codebase, start here and follow the reading order below.

## Audience

- Engineering leads and backend developers
- Frontend developers integrating the APIs
- Product and delivery owners
- Ops and infrastructure owners

## Reading Order (recommended)

1) 00-product-brief.md
2) 01-architecture-overview.md
3) 02-backend-architecture.md
4) 03-run-lifecycle.md
5) 04-chat-router.md
6) 05-api-reference.md
7) 06-data-models.md
8) 07-llm-prompts.md
9) 08-config-and-env.md
10) 09-dev-setup.md
11) 10-testing.md
12) 11-ops-deploy.md
13) 12-security-safety.md
14) 13-frontend-integration.md
15) 14-known-issues.md
16) 15-roadmap.md
17) 16-decision-log.md
18) 17-glossary.md
19) 18-postman-testing.md
20) 19-step-by-step-ui-integration.md
21) 20-checkpointing-ui.md

## Ownership

- Primary owner: (fill in)
- Tech lead: (fill in)
- Product owner: (fill in)
- Ops owner: (fill in)

Update this section as team ownership changes.

## Doc conventions

- Use plain Markdown.
- Keep all URLs in a separate "References" subsection when possible.
- Use inline code for paths, endpoints, and JSON keys.
- When adding diagrams, store them in `docs/project/assets/` and link from the
  relevant document.
- If a document is updated, add a short "Change log" note at the bottom.

## Quick links to existing docs

- `docs/architecture-overview.md`
- `docs/frontend_integration.md`
- `docs/ui-demo-spec.md`

These are still in use. If you edit or move them, update this hub.

## How to update this hub

1) Make a small, focused change.
2) Note the change in the document "Change log".
3) If a contract changes, also update `05-api-reference.md` and
   `06-data-models.md`.
4) If safety behavior changes, update `12-security-safety.md`.

## Goals for the hub

- The next team can run the system locally in under 30 minutes.
- The next team can reason about run behavior without reading code.
- The next team can extend flows without breaking safety guarantees.

## Change log

- 2026-01-13: Added the step-by-step UI integration doc to the reading order.
- 2026-01-15: Add UI checkpointing guide to the reading order.

