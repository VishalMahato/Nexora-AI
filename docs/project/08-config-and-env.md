# Config and Environment

## Purpose

List all configuration knobs, defaults, and how to change them safely.

## Source of Truth

Settings live in:

- `app/config.py`
- `.env` (optional local overrides)

## Core Settings

Database:

- `DATABASE_URL`

LLM:

- `LLM_ENABLED` (true/false)
- `LLM_MODEL` (default `gpt-4o-mini`)
- `LLM_PROVIDER` (default `openai`)
- `OPENAI_API_KEY`
- `LLM_TEMPERATURE` (planner/judge)
- `LLM_CHAT_TEMPERATURE` (chat response)
- `LLM_CHAT_RESPONSES` (true/false)
- `LLM_TIMEOUT_S`

RPC:

- `RPC_URLS` (comma or JSON, see chain client)
- `WEB3_SERVICE_URL` (if used)

Allowlists:

- `ALLOWLIST_TO`
- `ALLOWLIST_TO_ALL` (true/false, disable target allowlist checks for local dev)
- `ALLOWLISTED_TOKENS`
- `ALLOWLISTED_ROUTERS`

DeFi defaults:

- `DEX_KIND`
- `DEFAULT_SLIPPAGE_BPS`
- `DEFAULT_DEADLINE_SECONDS`
- `MIN_SLIPPAGE_BPS`
- `MAX_SLIPPAGE_BPS`

Observability:

- `LOG_LEVEL`
- `LOG_JSON`
- `LANGSMITH_TRACING`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`
- `LANGSMITH_ENDPOINT`

## Allowlist Format

Tokens:

```
ALLOWLISTED_TOKENS = {
  "1": {
    "USDC": { "address": "...", "decimals": 6 },
    "WETH": { "address": "...", "decimals": 18 }
  }
}
```

Routers:

```

Targets:

```
ALLOWLIST_TO = ["0xabc...", "0xdef..."]
```

When `ALLOWLIST_TO_ALL=true`, target address checks are skipped (dev only).
ALLOWLISTED_ROUTERS = {
  "1": {
    "UNISWAP_V2_ROUTER": { "address": "0x..." }
  }
}
```

## Notes

- If `LLM_ENABLED` is false, chat and planner fall back to safe defaults.
- Keep allowlists minimal for demo safety.
- Changes to allowlists affect policy rules and compilation.

## Go-Live Defaults and Risk Notes

Recommended safe defaults for production-like environments:

- `ALLOWLIST_TO_ALL=false` (never bypass target allowlist checks).
- `ALLOWLIST_TO` set to explicit target addresses (avoid empty lists).
- `ALLOWLISTED_TOKENS` and `ALLOWLISTED_ROUTERS` only include supported assets.
- `RPC_URLS` includes only chains you allow in the allowlists.
- `DEX_KIND=uniswap_v2` (only supported value today).
- `DEFAULT_SLIPPAGE_BPS` within [`MIN_SLIPPAGE_BPS`, `MAX_SLIPPAGE_BPS`].
- `DEFAULT_DEADLINE_SECONDS=1200` unless you have a reason to change it.
- `LLM_ENABLED=false` for strict determinism; if enabled, keep
  `LLM_TEMPERATURE=0.0` and `LLM_CHAT_TEMPERATURE<=0.5`.

Impact and failure modes to watch:

- `ALLOWLIST_TO` empty or invalid JSON skips the target allowlist check.
- `ALLOWLIST_TO_ALL=true` allows any transfer target (dev only).
- Missing tokens/routers in allowlists cause policy BLOCK for swaps.
- `RPC_URLS` missing a chain causes UnsupportedChain errors at runtime.
- `DEX_KIND` values other than `uniswap_v2` raise errors in `BUILD_TXS`.
- Slippage defaults outside bounds cause policy BLOCK.
- Enabling LLM without keys or with high temperature can cause plan instability
  or fallbacks.

## Change log

- 2026-01-14: Clarify target allowlist format and bypass flag.
- 2026-01-15: Add go-live defaults and risk notes.

