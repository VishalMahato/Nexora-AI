
# Project Notes

This document contains internal context, design decisions, constraints,
and non-obvious details that do not belong in the public README.

It acts as the project’s long-term memory.

---

## 1. Why Postgres Is Required And Used For

Postgres is the system of record for this project.

It is used for:
- Checkpointing LangGraph workflow state
- Persisting audit trails (intent → plan → simulation → decision)
- Enabling pause/resume for human approval
- Ensuring recoverability across restarts or deployments

This is not optional for a safe, multi-step system.

---

## 2. Why LangGraph (Instead of Plain Async Code)

LangGraph provides:
- Explicit state transitions
- Deterministic execution paths
- Native support for pause/resume flows
- Clear separation between AI reasoning and control logic

This significantly reduces the risk of unintended execution.

---

## 3. Safety Model (Critical)

- The LLM **never** crafts raw transaction calldata.
- All transactions are built using pre-defined templates.
- Deterministic validators always override LLM output.
- Human approval is mandatory in the MVP.

The system is designed so that AI suggestions are advisory, not authoritative.

---

## 4. Explicit Non-Goals (MVP Scope)

This MVP intentionally does NOT:
- Sign or broadcast transactions
- Handle private keys
- Execute arbitrary contract calls
- Perform cross-chain or complex strategies

These constraints are deliberate for safety and clarity.

---

## 5. Supabase Usage Notes

- Supabase is used strictly as a managed Postgres provider.
- Auth, storage, and edge functions are intentionally unused.
- Connection pooling is preferred for FastAPI workloads.

This keeps infra simple and portable.

---

## 6. Known Limitations

- Single-chain support
- Limited allowlist of tokens and routers
- Manual approval required for every run
- No automated risk thresholds yet

These are acceptable trade-offs for an MVP.

---

## 7. Future Directions (Out of Scope)

- Policy-as-code UI
- Automated approval for low-risk actions
- Multi-chain expansion
- Formal evaluation and scoring pipelines