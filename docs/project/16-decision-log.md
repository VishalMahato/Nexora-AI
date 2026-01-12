# Decision Log

## Format

Each entry includes:

- Date
- Decision
- Rationale
- Consequences

## Entries

### 2026-01-11: Chat router separated from run graph

- Decision: Keep conversational LLM outside the run graph. Runs are created only
  for actionable intents.
- Rationale: Faster UX, fewer run IDs, and clearer audit boundary.
- Consequences: Chat router must manage clarify follow-ups and tool queries.

### 2026-01-11: No backend signing

- Decision: Backend never signs or broadcasts transactions.
- Rationale: Reduce security risk and keep demo safe.
- Consequences: Frontend must handle signing and execution.

### 2026-01-12: Query intents forced to QUERY

- Decision: If `intent_type` is a query (snapshot/balance/allowlists), router
  always forces `mode=QUERY` regardless of classifier output.
- Rationale: Prevent accidental run creation for read-only requests.
- Consequences: Router normalization is required for stability.
