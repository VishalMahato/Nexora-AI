# Testing

## Overview

Tests are written with pytest and focus on deterministic behavior. LLM calls
are mocked in unit tests; RPC calls are mocked where possible.

## How to Run

Run all tests:

```
pytest
```

Run a specific file:

```
pytest tests/test_chat_query_tools.py
```

## Test Categories

1) Chat Router
   - Classification mapping
   - Query tools
   - Clarify follow-ups

2) Planner + Policy
   - LLM planner contract
   - Policy rules and decision mapping

3) DeFi Compiler
   - Approve + swap compilation
   - Allowlist checks

4) Simulation
   - Sequential simulation
   - Assumed success warnings

5) API Integration
   - Run creation and start
   - Approval and execute flows

## Mocking Strategy

- LLM functions are patched via `app.chat.router.classify_intent` or
  `llm.client.LLMClient` depending on test.
- RPC calls are mocked in chain client tests.

## Common Pitfalls

- Long-running RPC calls can cause timeouts in tests.
- Ensure `LLM_ENABLED` is false in tests unless explicitly mocked.
- If using Supabase for `DATABASE_URL`, expect occasional connection resets;
  local Postgres is more reliable for full test runs.

## Change log

- 2026-01-14: Note Supabase connection resets in tests.

