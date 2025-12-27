## Git Workflow (Production-Oriented)

### Branching Strategy
- `main` is always stable and deployable.
- No direct commits are made to `main`.
- All work is done on short-lived feature branches.

**Branch naming conventions**
- `feat/<feature-name>` — user-facing functionality
- `chore/<task-name>` — setup, refactors, infra, tooling
- `fix/<issue-name>` — bug fixes

This keeps intent clear and history readable at scale.

---

### Commit Convention
We follow **Conventional Commits** to keep history structured and automation-friendly.

Common prefixes:
- `feat:` new functionality
- `chore:` scaffolding, infra, maintenance
- `fix:` bug fixes

Example:
```text
chore: bootstrap fastapi app skeleton
