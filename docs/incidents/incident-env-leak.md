# Incident Report: Accidental `.env` Tracking & Recovery

## Summary

During early project setup, a local `.env` file was accidentally tracked on the remote `master` branch.
Although the file did not contain sensitive secrets, the situation was treated as a **security incident**
and resolved using production-grade Git workflows to restore repository hygiene and prevent recurrence.

This document records **what happened**, **how it was detected**, **how it was fixed**, and
**what commands were used**, in chronological order.

---

## Timeline

### 1. Initial Setup
- Project scaffolding (F1) was completed.
- A local `.env` file existed for development configuration.
- `.gitignore` was updated later to include `.env`.

At this stage, it was assumed `.env` was not tracked.

---

### 2. Detection
While reviewing the GitHub repository UI, `.env` appeared in the file list on the `master` branch.
This raised a concern because `.env` files must never be committed.

---

### 3. Verification (Source of Truth)
Local checks initially showed `.env` was not present on the local `master` branch.

To verify the remote state, the remote branch was inspected directly:

```bash
git fetch origin
git ls-tree -r --name-only origin/master | grep '^\.env$'
```

**Result:** `.env` was confirmed to be tracked on `origin/master`.

Conclusion:
> The remote `master` branch contained `.env`, even though the local branch did not.

---

## Decision

Following production standards:
- Security issues must be fixed **before** feature work.
- The issue should be resolved via a **hotfix PR** to maintain auditability.

Decision:
- Create a dedicated hotfix branch.
- Remove `.env` from version control.
- Harden `.gitignore`.
- Merge the fix before continuing feature development.

---

## Resolution Steps

### 1. Create Hotfix Branch from Remote `master`
```bash
git checkout -b fix/remove-env origin/master
```

### 2. Remove `.env` from Version Control
```bash
git rm --cached .env
```

### 3. Harden `.gitignore`
```gitignore
.env
.env.*
```

```bash
git add .gitignore
git commit -m "fix: remove .env from repository"
```

### 4. Push Hotfix Branch
```bash
git push -u origin fix/remove-env
```

### 5. Hotfix PR
- Base branch: `master`
- Compare branch: `fix/remove-env`
- Merge strategy: **Squash merge**

---

### 6. Sync Local Repository
```bash
git checkout master
git pull
git fetch --prune
```

---

## Feature Branch Recovery

### Rebase on Clean `master`
```bash
git checkout chore/config-loader
git rebase master
```

### Conflict Resolution
Final `.gitignore`:
```gitignore
.env
.env.*
```

```bash
git add .gitignore
git rebase --continue
git push --force-with-lease
```

---

## Lessons Learned

- `.gitignore` does not affect files already tracked by Git.
- Always verify against `origin/<branch>`.
- Security fixes must land before features.
- Rebase keeps history clean.
- Incidents should be documented even if no secrets leak.

---

## Final State

- `master` is clean and secure.
- `.env` is no longer tracked.
- Feature branch successfully rebased.
