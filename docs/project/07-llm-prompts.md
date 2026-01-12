# LLM Prompts and Contracts

## Purpose

Describe how LLMs are used, which prompts exist, and what output contracts
must be preserved. This is essential for safe changes and debugging.

## LLM Usage Summary

LLM is used for:

- Intent classification in chat router
- Planner (PLAN_TX)
- Judge agent (JUDGE_AGENT)
- Repair planner (optional)
- Chat response polishing (assistant_message rewrite)

All LLM outputs are JSON-only and validated.

## Chat Router Prompts

### Intent Classifier

File: `app/chat/prompts.py`

Required JSON keys:

- `mode`
- `intent_type`
- `confidence`
- `slots`
- `missing_slots`
- `reason`

Modes:

- QUERY
- ACTION
- CLARIFY
- GENERAL

Notes:

- Uses conversation history when provided.
- Router normalizes mode to QUERY for query intents.

### Chat Response Polisher

File: `app/chat/prompts.py`

Input:

- `draft` (assistant_message)
- `context` (mode, intent_type, user_message, status)

Output:

```
{ "message": "..." }
```

Constraints:

- Preserve factual data (numbers, addresses).
- Keep line breaks.
- Do not invent new facts.

## Planner Prompt

File: `llm/prompts.py`

Output JSON:

- `plan_version`
- `type`
- `normalized_intent`
- `actions[]`
- `candidates[]`

Constraints:

- Deterministic output
- No cycles, no signing

## Judge Prompt

File: `llm/prompts.py`

Output JSON:

```
{
  "verdict": "PASS|NEEDS_REWORK|BLOCK",
  "reasoning_summary": "...",
  "issues": [ ... ]
}
```

Constraints:

- No chain-of-thought
- Provide structured issues

## Repair Prompt

File: `llm/prompts.py`

Input includes:

- prior plan summary
- judge issues

Output matches planner contract.

## Temperature Settings

Config (see `app/config.py`):

- `LLM_TEMPERATURE` (planner/judge)
- `LLM_CHAT_TEMPERATURE` (assistant response)

## Versioning Guidance

- If prompt structure changes, bump the version in output.
- Update tests that validate schema.

## Failure Handling

If LLM output is invalid:

- Fallback to safe CLARIFY (chat)
- Fallback to noop plan (planner)
- WARN and require manual review (judge)

