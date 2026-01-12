# Known Issues and Limitations

## Simulation Assumptions

Sequential simulation uses guarded assumptions when allowances cannot be applied
in stateless `eth_call`. This can produce WARN results even when policy passes.

Impact:

- Demo is safe but not fully stateful.
- F24b (state override) is pending.

## In-Memory Chat State

Conversation pending state is stored in memory with TTL. It will reset on app
restart and is not shared across instances.

Impact:

- Load-balanced deployments can lose pending state.
- Multi-instance deployments need shared storage.

## LLM Variability

LLM outputs are constrained to JSON, but occasional invalid outputs can occur.
The system falls back to safe defaults in these cases.

Impact:

- Some user queries may be answered with CLARIFY unexpectedly.
- Additional examples in prompts can reduce this.

## Multi-Intent Conversations

Only one ACTION intent is supported per conversation. Multi-intent dialog
management is deferred.

Impact:

- Users must finish a flow before starting another ACTION.
