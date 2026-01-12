# Glossary

- ACTION: Chat mode that creates and starts a run.
- QUERY: Chat mode for read-only responses without runs.
- CLARIFY: Chat mode that asks for missing fields.
- GENERAL: Chat mode for smalltalk and general questions.
- Run: A single execution of the LangGraph pipeline.
- tx_plan: Planner output describing actions and candidates.
- tx_requests: Transaction requests returned for frontend signing.
- AgentResult: Standard agent output contract with explanation.
- Timeline: UI-friendly list of step summaries.
- Policy result: Structured checks with pass/warn/fail statuses.
- Decision: Final policy decision with severity and reasons.
- Artifacts: All outputs produced by a run (planner, simulation, policy, etc).
- assumed_success: Simulation flag when a swap is assumed safe after approve.
- Allowlist: Configured list of allowed tokens and routers.
- Judge: LLM reviewer that produces PASS/NEEDS_REWORK/BLOCK.
