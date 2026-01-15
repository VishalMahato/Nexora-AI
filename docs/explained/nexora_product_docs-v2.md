# Nexora AI - Product Documentation

Note: For current run pipeline, status mapping, and API contracts, refer to:
- docs/project/03-run-lifecycle.md
- docs/project/05-api-reference.md
- docs/project/06-data-models.md

## Executive Summary

Nexora AI is a blockchain intent execution system that interprets natural language user requests and orchestrates safe, policy-compliant smart contract interactions. The system features enterprise-grade auditability, FSM-based execution flow, real-time Web3 integration, and a comprehensive policy engine for risk management.

**Current Version:** 0.2.0  
**Build Status:** Production-Ready MVP  
**Latest Release:** F13 (Approval Gate) - January 2026

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Concepts](#core-concepts)
3. [System Components](#system-components)
4. [Complete Feature Breakdown](#complete-feature-breakdown)
5. [API Reference](#api-reference)
6. [Database Schema](#database-schema)
7. [Policy Engine](#policy-engine)
8. [Web3 Integration](#web3-integration)
9. [Development Guide](#development-guide)
10. [Testing Strategy](#testing-strategy)
11. [Deployment Guide](#deployment-guide)
12. [Roadmap](#roadmap)

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLIENT LAYER                           │
│  Web/Mobile App → Natural Language Intent → Wallet Address  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI APPLICATION                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              API Layer (v1)                         │   │
│  │  • POST /v1/runs - Create Run                       │   │
│  │  • POST /v1/runs/{id}/start - Execute               │   │
│  │  • POST /v1/runs/{id}/approve - Approve             │   │
│  │  • POST /v1/runs/{id}/reject - Reject               │   │
│  │  • GET  /v1/runs/{id}/tools - Tool Call Timeline    │   │
│  └────────────────────┬────────────────────────────────┘   │
│                       │                                     │
│  ┌────────────────────▼────────────────────────────────┐   │
│  │         LangGraph Orchestration Engine              │   │
│  │                                                      │   │
│  │  INPUT_NORMALIZE → WALLET_SNAPSHOT → BUILD_TXS      │   │
│  │       ↓                                              │   │
│  │  SIMULATE_TXS → POLICY_EVAL → FINALIZE              │   │
│  └────────────────────┬────────────────────────────────┘   │
│                       │                                     │
│  ┌────────────────────▼────────────────────────────────┐   │
│  │            Business Logic Layer                     │   │
│  │  • Policy Engine (rules + risk scoring)             │   │
│  │  • Web3 Client (on-chain state reads)               │   │
│  │  • Tool Runner (instrumentation wrapper)            │   │
│  └────────────────────┬────────────────────────────────┘   │
│                       │                                     │
│  ┌────────────────────▼────────────────────────────────┐   │
│  │          Repository Layer                           │   │
│  │  • RunsRepo - FSM state management                  │   │
│  │  • RunStepsRepo - Audit trail logging               │   │
│  │  • ToolCallsRepo - External call tracking           │   │
│  └────────────────────┬────────────────────────────────┘   │
└────────────────────────┼──────────────────────────────────┘
                         │
                         ▼
      ┌──────────────────────────────────────┐
      │        PostgreSQL Database           │
      │  • runs (FSM state)                  │
      │  • run_steps (audit log)             │
      │  • tool_calls (observability)        │
      └──────────────────┬───────────────────┘
                         │
                         ▼
      ┌──────────────────────────────────────┐
      │       External Integrations          │
      │  • Ethereum RPC (via web3.py)        │
      │  • Polygon RPC                       │
      │  • LangSmith (optional tracing)      │
      └──────────────────────────────────────┘
```

### Technology Stack

**Core Framework:**
- Python 3.12 (strict version requirement)
- FastAPI 0.128+ (async API framework)
- LangGraph 1.0+ (workflow orchestration)
- Pydantic 2.12+ (data validation)

**Database:**
- PostgreSQL 14+ (primary data store)
- SQLAlchemy 2.0 (ORM with typed mappings)
- Alembic (schema migrations)

**Blockchain:**
- web3.py 7.14+ (Ethereum interaction)
- eth-abi 5.0+ (ABI encoding/decoding)

**Observability:**
- Structured logging (JSON/text)
- LangSmith (optional distributed tracing)
- Custom middleware (request correlation)

**Development:**
- uv (fast package management)
- pytest (testing framework)
- ruff (linting & formatting)

---

## Core Concepts

### 1. Run Entity

A **Run** is the fundamental unit of execution representing a single user intent from submission to completion.

**Properties:**
- `id` - Unique UUID identifier
- `intent` - Natural language user request (1-5000 chars)
- `wallet_address` - Ethereum address (checksummed)
- `chain_id` - Network identifier (1=Ethereum, 137=Polygon, etc.)
- `status` - Current FSM state
- `error_code` / `error_message` - Failure diagnostics
- `created_at` / `updated_at` - Temporal metadata

**Immutability Rules:**
- `intent`, `wallet_address`, `chain_id` are immutable after creation
- Only `status` and error fields can be updated
- All updates are atomic and logged

### 2. Finite State Machine (FSM)

The system enforces strict state transitions to ensure data integrity and auditability.

```
                    CREATED
                       │
                       ├─────> RUNNING ─────┐
                       │          │         │
                       │          ▼         ▼
                       │    AWAITING_    FAILED
                       │     APPROVAL      
                       │          │         
                       │          ├──> APPROVED_READY
                       │          │
                       │          ├──> REJECTED
                       │          │
                       │          └──> BLOCKED
                       │
                       └─────> (invalid transitions rejected)
```

**State Definitions:**

| Status | Description | Terminal? | Next States |
|--------|-------------|-----------|-------------|
| `CREATED` | Initialized, not started | No | `RUNNING` |
| `RUNNING` | Active execution | No | `AWAITING_APPROVAL`, `FAILED`, `BLOCKED` |
| `AWAITING_APPROVAL` | Ready for user decision | No | `APPROVED_READY`, `REJECTED` |
| `APPROVED_READY` | User approved, ready for broadcast | Yes | - |
| `FAILED` | Execution error | Yes | - |
| `REJECTED` | User rejected transaction | Yes | - |
| `BLOCKED` | Policy violation detected | Yes | - |

**Transition Rules:**
- Terminal states cannot transition further
- Optimistic locking prevents concurrent modifications
- Invalid transitions throw `ValueError`
- All transitions are logged in `run_steps` table

### 3. Run Steps (Audit Trail)

Each discrete phase of execution is logged as a **Run Step**, providing complete transparency and debuggability.

**Step Lifecycle:**
```python
# Step starts
log_step(db, run_id, step_name="WALLET_SNAPSHOT", status="STARTED", 
         input={"chainId": 1, "wallet": "0x..."}, agent="GRAPH")

# Step completes
log_step(db, run_id, step_name="WALLET_SNAPSHOT", status="DONE", 
         output={"native": {"balanceWei": "123..."}}, agent="GRAPH")
```

**Standard Step Names:**
- `RUN_CREATED` - Initial run creation
- `INPUT_NORMALIZE` - Intent sanitization
- `WALLET_SNAPSHOT` - On-chain state capture
- `BUILD_TXS` - Transaction planning
- `SIMULATE_TXS` - Transaction simulation
- `POLICY_EVAL` - Risk assessment
- `HUMAN_APPROVAL` - User decision
- `FINALIZE` - Completion handler

### 4. Tool Calls (Observability)

All external system interactions are instrumented via the **Tool Call** mechanism, enabling performance monitoring and debugging.

**Tool Call Pattern:**
```python
result = run_tool(
    db, run_id=run_id, step_id=step.id,
    tool_name="web3.eth_getBalance",
    request={"chainId": 1, "address": "0x..."},
    fn=lambda: rpc.get_native_balance(1, "0x...")
)
```

**Automatically Captured:**
- Request parameters (JSONB)
- Response data (JSONB)
- Execution timing (started_at, ended_at)
- Error messages (if failed)
- Association with run and step

**Common Tool Names:**
- `web3.eth_getBalance` - Native balance query
- `web3.erc20.balanceOf` - Token balance query
- `web3.erc20.allowance` - Approval amount query
- `web3.eth_call` - Transaction simulation
- `web3.estimate_gas` - Gas estimation
- `api_create_run` - API-level operation

### 5. Policy Engine

The **Policy Engine** evaluates transaction safety using a rule-based system with risk scoring.

**Policy Check Workflow:**
```
Artifacts → Rule Evaluation → Policy Result → Decision
```

**Check Statuses:**
- `PASS` - Rule satisfied
- `WARN` - Potential issue, increases risk score
- `FAIL` - Critical failure, blocks execution

**Decision Actions:**
- `ALLOW` - Auto-approved (future use)
- `NEEDS_APPROVAL` - Requires user confirmation
- `BLOCK` - Execution prohibited

**Risk Scoring:**
- WARN checks contribute 15 points each
- FAIL checks result in 100 (automatic block)
- Final score determines severity (LOW/MED/HIGH)

**Core Rules:**
1. **Required Artifacts** - Ensures all necessary data is present
2. **No Broadcast Invariant** - Prevents unauthorized signing
3. **Allowlist Targets** - Validates transaction recipients
4. **Simulation Success** - Requires successful dry-run

---

## Complete Feature Breakdown

### ✅ Phase 1: Foundation (F1-F13) - COMPLETE

#### F1-F3: Repository Bootstrap ✅
**Delivered:** Project scaffolding, dependency management, database foundation

**Infrastructure:**
- `pyproject.toml` - Project metadata and dependencies
- `uv.lock` - Reproducible dependency resolution
- `.python-version` - Python 3.12 pinning
- `.gitignore` - VCS hygiene rules
- `.env.example` - Configuration template

**Database Setup:**
- SQLAlchemy 2.0 with typed ORM
- Alembic migration framework
- `db/base.py` - Declarative base
- `db/session.py` - Engine and session factory
- `alembic.ini` - Migration configuration

#### F4: Runs API + Database Plumbing ✅
**Delivered:** Core run management with FSM enforcement

**Database Model:**
```python
class Run(Base):
    __tablename__ = "runs"
    id: UUID
    intent: str
    wallet_address: str
    chain_id: int
    status: str  # FSM-controlled
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

**Repository Layer:**
- `create_run()` - Initialize with CREATED status
- `get_run()` - Retrieve by ID
- `update_run_status()` - FSM-guarded transitions with optimistic locking

**API Endpoints:**
- `POST /v1/runs` - Create new run
- `GET /v1/runs/{id}` - Retrieve run details

**Custom Exceptions:**
- `RunNotFoundError` - Run doesn't exist
- `RunStatusConflictError` - Concurrent modification detected

#### F5: Run Steps Logging ✅
**Delivered:** Complete audit trail for execution phases

**Database Model:**
```python
class RunStep(Base):
    __tablename__ = "run_steps"
    id: UUID
    run_id: UUID  # FK to runs
    step_name: str
    agent: str | None  # LangGraph, API, GRAPH
    status: str  # STARTED, DONE, FAILED
    input: JSONB | None
    output: JSONB | None
    error: str | None
    started_at: datetime
    ended_at: datetime | None
```

**Repository Functions:**
- `log_step()` - Insert step record with auto-timestamps
- `list_steps_for_run()` - Chronological retrieval

**Indexes:**
- `(run_id, started_at)` - Timeline queries
- `(run_id, step_name)` - Step lookup

#### F6: Tool Calls Table ✅
**Delivered:** Instrumentation infrastructure for external calls

**Database Model:**
```python
class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: UUID
    run_id: UUID  # FK to runs
    step_id: UUID | None  # FK to run_steps
    tool_name: str
    request: JSONB | None
    response: JSONB | None
    error: str | None
    started_at: datetime
    ended_at: datetime | None
```

**Repository Functions:**
- `start_tool_call()` - Begin tracking
- `finish_tool_call()` - Record completion
- `log_tool_call()` - One-shot logging
- `list_tool_calls_for_run()` - Chronological retrieval

**Indexes:**
- `(run_id, started_at)` - Run timeline
- `(step_id)` - Step association
- `(tool_name, started_at)` - Performance analytics

#### F7: Database Finalization ✅
**Delivered:** Schema stability and model exports

**Completed:**
- All models exported via `db/models/__init__.py`
- Foreign key relationships validated
- Cascade rules configured
- Migration history clean
- Tests passing (20+ test cases)

#### F8: Observability Infrastructure ✅
**Delivered:** Production-grade logging and tracing

**Structured Logging:**
```python
# Configuration
LOG_LEVEL=INFO      # DEBUG, INFO, WARNING, ERROR
LOG_JSON=false      # true for production
```

**Features:**
- Automatic `run_id` injection in all logs
- UTC timestamps for consistency
- Configurable JSON or text output
- Noise control for verbose libraries

**Components:**
- `app/core/context.py` - Contextvars for run_id
- `app/core/logging.py` - Formatters and filters
- `app/core/middleware.py` - Request lifecycle management

**LangSmith Integration (Optional):**
```python
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<key>
LANGSMITH_PROJECT=nexora-ai
```

**Capabilities:**
- Distributed tracing for LangGraph workflows
- Node-level I/O inspection
- Performance profiling
- Error attribution

#### F8 (Extended): LangGraph Execution Engine ✅
**Delivered:** Workflow orchestration with database integration

**Graph Structure:**
```
START → INPUT_NORMALIZE → WALLET_SNAPSHOT → BUILD_TXS
              ↓
      SIMULATE_TXS → POLICY_EVAL → FINALIZE → END
```

**State Management:**
```python
class RunState(BaseModel):
    run_id: UUID
    intent: str
    status: RunStatus
    chain_id: int | None
    wallet_address: str | None
    artifacts: Dict[str, Any]  # Inter-node data passing
```

**Node Responsibilities:**
- `input_normalize` - Sanitize intent string
- `wallet_snapshot` - Capture on-chain state
- `build_txs` - Plan transaction candidates
- `simulate_txs` - Dry-run transactions
- `policy_eval` - Risk assessment
- `finalize` - Cleanup and final logging

**Database Session Passing:**
```python
config = {"configurable": {"db": db}}
result = app.invoke(state.model_dump(), config=config)
```

#### F9: LangSmith Integration (Optional) ✅
**Delivered:** Non-breaking observability enhancement

**Features:**
- Graceful degradation when disabled
- Safe callback injection
- Metadata-rich traces

**Tests:**
- App starts without LangSmith vars
- App starts when tracing disabled
- No runtime errors on missing configuration

#### F10: Tool Call Instrumentation ✅
**Delivered:** Generic wrapper for external calls

**Implementation:**
```python
def run_tool(db, *, run_id, step_id, tool_name, request, fn):
    tool_call = start_tool_call(db, run_id, step_id, tool_name, request)
    try:
        result = fn()
        finish_tool_call(db, tool_call.id, response=result)
        return result
    except Exception as e:
        finish_tool_call(db, tool_call.id, error=str(e))
        raise
```

**Benefits:**
- Automatic timing capture
- Error tracking
- Performance analytics
- Zero boilerplate in calling code

#### F11: Web3 Integration ✅
**Delivered:** On-chain state reading via web3.py

**Chain Configuration:**
```python
# .env
RPC_URLS='{"1":"https://eth.llamarpc.com","137":"https://polygon.llamarpc.com"}'
```

**ChainClient Features:**

**Wallet Snapshot:**
```python
snapshot = client.wallet_snapshot(
    db=db, run_id=run_id, step_id=step.id,
    chain_id=1,
    wallet_address="0x...",
    erc20_tokens=["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"],  # USDC
    allowances=[{"token": "0x...", "spender": "0x..."}]
)
```

**Returns:**
```json
{
  "chainId": 1,
  "walletAddress": "0x...",
  "native": {"balanceWei": "1500000000000000000"},
  "erc20": [
    {
      "token": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
      "symbol": "USDC",
      "decimals": 6,
      "balance": "50000000"
    }
  ],
  "allowances": [
    {
      "token": "0x...",
      "spender": "0x...",
      "allowance": "115792089237316195423570985008687907853269984665640564039457584007913129639935"
    }
  ]
}
```

**Transaction Builders:**
- `build_approve_tx()` - ERC20 approval template
- `build_swap_tx()` - DEX swap template (placeholder)

**Simulation:**
```python
result = client.simulate_tx(
    db=db, run_id=run_id, step_id=step.id,
    chain_id=1,
    tx={"from": "0x...", "to": "0x...", "data": "0x..."}
)
```

**RPC Layer (`chain/rpc.py`):**
- `get_native_balance()` - ETH/MATIC balance
- `erc20_balance()` - Token balance
- `erc20_allowance()` - Approval amount
- `erc20_decimals()` - Token decimals
- `erc20_symbol()` - Token symbol
- `eth_call()` - Call without state change
- `estimate_gas()` - Gas estimation

**Error Handling:**
- `Web3RPCError` - Network/RPC failures
- `UnsupportedChainError` - Chain not configured
- `ContractLogicError` - Revert detection

#### F12: Policy Engine ✅
**Delivered:** Rule-based risk assessment system

**Architecture:**
```python
def evaluate_policies(artifacts, *, allowlisted_to):
    checks = [
        rule_required_artifacts_present(artifacts),
        rule_no_signing_broadcast_invariant(artifacts),
        rule_allowlist_targets(artifacts, allowlisted_to),
        rule_simulation_success(artifacts),
    ]
    
    result = PolicyResult(checks=checks)
    decision = _make_decision(checks)
    return result, decision
```

**Rule: Required Artifacts**
- Ensures `wallet_snapshot`, `tx_plan`, `simulation` exist
- Status: FAIL if missing
- Purpose: Prevent incomplete evaluation

**Rule: No Broadcast Invariant**
- Checks `tx_plan.broadcast != True`
- Status: FAIL if broadcast requested
- Purpose: Enforce custody safety

**Rule: Allowlist Targets**
```python
# Configuration
ALLOWLIST_TO='["0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"]'  # Uniswap V2 Router

# Evaluation
def rule_allowlist_targets(artifacts, allowlisted_to):
    for tx in artifacts["tx_plan"]["candidates"]:
        if tx["to"].lower() not in allowlisted_to:
            return FAIL
    return PASS
```

**Rule: Simulation Success**
- Checks simulation didn't revert
- Status: FAIL if reverted, WARN if skipped
- Purpose: Catch execution errors pre-flight

**Risk Scoring:**
```python
score = sum(15 for check in checks if check.status == "WARN")
if any(check.status == "FAIL" for check in checks):
    score = 100  # Automatic block
```

**Decision Logic:**
```python
if has_fail:
    action = "BLOCK"
    severity = "HIGH"
else:
    action = "NEEDS_APPROVAL"  # MVP: always require human approval
    severity = "LOW" if score < 25 else "MED" if score < 60 else "HIGH"
```

**Integration:**
```python
# In graph/nodes.py
def policy_eval(state, config):
    policy_result, decision = policy_engine.evaluate_policies(
        state.artifacts,
        allowlisted_to=settings.allowlisted_to_set()
    )
    
    state.artifacts["policy_result"] = policy_result.model_dump()
    state.artifacts["decision"] = decision.model_dump()
    return state
```

#### F13: Approval Gate ✅
**Delivered:** Human-in-the-loop decision point

**API Endpoints:**

**Approve:**
```python
POST /v1/runs/{run_id}/approve
{
  "reviewer": "alice@example.com",
  "notes": "Verified swap parameters"
}

Response:
{
  "ok": true,
  "runId": "...",
  "status": "APPROVED_READY"
}
```

**Reject:**
```python
POST /v1/runs/{run_id}/reject
{
  "reviewer": "bob@example.com",
  "reason": "Slippage too high"
}

Response:
{
  "ok": true,
  "runId": "...",
  "status": "REJECTED"
}
```

**State Transitions:**
```
AWAITING_APPROVAL → APPROVED_READY  (via /approve)
AWAITING_APPROVAL → REJECTED        (via /reject)
```

**Error Handling:**
- 404 if run not found
- 409 if not in `AWAITING_APPROVAL` status
- 409 if run is `BLOCKED` (policy violation)

**Audit Trail:**
```python
log_step(
    db, run_id=run_id,
    step_name="HUMAN_APPROVAL",
    status="STARTED",
    input={
        "action": "APPROVE",
        "reviewer": "alice@example.com",
        "notes": "Verified swap parameters"
    },
    agent="API"
)
```

**Tests:**
- Happy path approval
- Happy path rejection
- 409 on approve before start
- 409 on approve blocked run
- Audit trail verification

---

## API Reference

### Base URL

```
Production: https://api.nexora.ai
Staging: https://staging-api.nexora.ai
Local: http://localhost:8000
```

### Authentication

**Current:** None (MVP)  
**Planned:** API key via `X-API-Key` header

### Common Headers

```
Content-Type: application/json
X-Run-Id: <uuid>  # Optional, for log correlation
```

### Endpoints

#### Create Run
```http
POST /v1/runs
Content-Type: application/json

{
  "intent": "Swap 50 USDC to ETH on Uniswap with 0.5% slippage",
  "walletAddress": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
  "chainId": 1
}
```

**Response (200):**
```json
{
  "runId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "CREATED"
}
```

**Validation Errors (422):**
- `walletAddress` must start with `0x`
- `intent` length: 1-5000 chars
- `chainId` must be ≥ 1

#### Get Run
```http
GET /v1/runs/550e8400-e29b-41d4-a716-446655440000
```

**Response (200):**
```json
{
  "run": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "intent": "Swap 50 USDC to ETH on Uniswap with 0.5% slippage",
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
    "chain_id": 1,
    "status": "AWAITING_APPROVAL",
    "error_code": null,
    "error_message": null,
    "created_at": "2026-01-07T10:30:45.123456Z",
    "updated_at": "2026-01-07T10:30:47.654321Z"
  }
}
```

#### Start Run Execution
```http
POST /v1/runs/550e8400-e29b-41d4-a716-446655440000/start
```

**Response (200) - Success:**
```json
{
  "ok": true,
  "runId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "AWAITING_APPROVAL",
  "artifacts": {
    "normalized_intent": "swap 50 usdc to eth on uniswap with 0.5% slippage",
    "wallet_snapshot": {
      "chainId": 1,
      "walletAddress": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
      "native": {"balanceWei": "1500000000000000000"},
      "erc20": [
        {
          "token": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
          "symbol": "USDC",
          "decimals": 6,
          "balance": "50000000"
        }
      ]
    },
    "tx_plan": {
      "type": "noop",
      "reason": "tx planning not implemented yet"
    },
    "simulation": {
      "status": "skipped"
    },
    "policy_result": {
      "checks": [
        {"id": "required_artifacts", "status": "PASS"},
        {"id": "no_broadcast", "status": "PASS"},
        {"id": "allowlist_targets", "status": "PASS"},
        {"id": "simulation_success", "status": "WARN"}
      ]
    },
    "decision": {
      "action": "NEEDS_APPROVAL",
      "risk_score": 15,
      "severity": "LOW",
      "summary": "Ready for review: policy checks completed.",
      "reasons": ["Simulation: must succeed: Simulation was skipped for a non-noop plan."]
    }
  }
}
```

**Response (200) - Blocked:**
```json
{
  "ok": true,
  "runId": "...",
  "status": "BLOCKED",
  "artifacts": {
    "decision": {
      "action": "BLOCK",
      "risk_score": 100,
      "severity": "HIGH",
      "summary": "Blocked: one or more required safety checks failed.",
      "reasons": ["Allowlist: transaction targets: Transaction targets include non-allowlisted addresses."]
    }
  }
}
```

**Error Responses:**
- 404 - Run not found
- 409 - Invalid state transition (already started)
- 500 - Execution failure

#### Approve Run
```http
POST /v1/runs/550e8400-e29b-41d4-a716-446655440000/approve
Content-Type: application/json

{
  "reviewer": "alice@example.com",
  "notes": "Verified parameters, approved"
}
```

**Response (200):**
```json
{
  "ok": true,
  "runId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "APPROVED_READY"
}
```

**Error Responses:**
- 404 - Run not found
- 409 - Run not in `AWAITING_APPROVAL` status

#### Reject Run
```http
POST /v1/runs/550e8400-e29b-41d4-a716-446655440000/reject
Content-Type: application/json

{
  "reviewer": "bob@example.com",
  "reason": "Slippage too high, rejecting"
}
```

**Response (200):**
```json
{
  "ok": true,
  "runId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "REJECTED"
}
```

#### Get Tool Calls
```http
GET /v1/runs/550e8400-e29b-41d4-a716-446655440000/tool-calls
```

**Response (200):**
```json
[
  {
    "id": "...",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "step_id": "...",
    "tool_name": "web3.eth_getBalance",
    "request": {"chainId": 1, "walletAddress": "0
