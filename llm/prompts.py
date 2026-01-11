from __future__ import annotations

import json
from typing import Any, Dict


SYSTEM_PROMPT = (
    "You are Nexora planner. Output ONLY valid JSON matching the TxPlan schema. "
    "Do not include markdown or commentary. "
    "Schema requirements: "
    "plan_version (int, use 1), type ('noop' or 'plan'), reason (string or null), "
    "normalized_intent (string), actions (list), candidates (list). "
    "Each candidate requires: chain_id (int), to (0x address), data (0x hex), "
    "valueWei (string). "
    "Respect allowlists and defaults. If unsure, return a noop plan with a reason."
)

REPAIR_PLAN_SYSTEM_PROMPT = (
    "You are Nexora planner repairing a prior plan. "
    "Use the judge issues and the previous plan summary to produce a corrected TxPlan. "
    "Return ONLY valid JSON matching the TxPlan schema. "
    "Do not include markdown or commentary. "
    "Schema requirements: "
    "plan_version (int, use 1), type ('noop' or 'plan'), reason (string or null), "
    "normalized_intent (string), actions (list), candidates (list). "
    "Each candidate requires: chain_id (int), to (0x address), data (0x hex), "
    "valueWei (string). "
    "If you cannot safely fix the plan, return a noop plan with a reason."
)

JUDGE_SYSTEM_PROMPT = (
    "You are Nexora judge. Review the inputs and return ONLY valid JSON that matches the JudgeOutput schema. "
    "No markdown or extra text. "
    "Schema requirements: verdict ('PASS'|'NEEDS_REWORK'|'BLOCK'), reasoning_summary (short string), "
    "issues (list of {code, severity ('LOW'|'MED'|'HIGH'), message, data}). "
    "Do not include chain-of-thought."
)


def build_plan_tx_prompt(planner_input: Dict[str, Any]) -> Dict[str, str]:
    user_payload = {
        "normalized_intent": planner_input.get("normalized_intent"),
        "chain_id": planner_input.get("chain_id"),
        "wallet_snapshot": planner_input.get("wallet_snapshot"),
        "allowlisted_tokens": planner_input.get("allowlisted_tokens"),
        "allowlisted_routers": planner_input.get("allowlisted_routers"),
        "defaults": planner_input.get("defaults"),
    }
    examples = [
        {
            "plan_version": 1,
            "type": "noop",
            "reason": "insufficient information or unsupported intent",
            "normalized_intent": "swap eth to usdc",
            "actions": [],
            "candidates": [],
        },
        {
            "plan_version": 1,
            "type": "plan",
            "normalized_intent": "send 0.01 eth to 0x1111111111111111111111111111111111111111",
            "actions": [
                {
                    "action": "TRANSFER",
                    "amount": "0.01",
                    "to": "0x1111111111111111111111111111111111111111",
                    "chain_id": 1,
                    "meta": {"asset": "ETH"},
                }
            ],
            "candidates": [
                {
                    "chain_id": 1,
                    "to": "0x1111111111111111111111111111111111111111",
                    "data": "0x",
                    "valueWei": "10000000000000000",
                    "meta": {"asset": "ETH"},
                }
            ],
        },
    ]
    user = (
        "Plan a transaction using the provided input. "
        "Return ONLY JSON that matches the schema.\n"
        f"Examples: {json.dumps(examples, ensure_ascii=True)}\n"
        f"Input: {json.dumps(user_payload, ensure_ascii=True)}"
    )
    return {"system": SYSTEM_PROMPT, "user": user}


def build_repair_plan_tx_prompt(repair_input: Dict[str, Any]) -> Dict[str, str]:
    examples = [
        {
            "plan_version": 1,
            "type": "noop",
            "reason": "could not resolve judge issues safely",
            "normalized_intent": "swap eth to usdc",
            "actions": [],
            "candidates": [],
        },
        {
            "plan_version": 1,
            "type": "plan",
            "normalized_intent": "send 0.01 eth to 0x1111111111111111111111111111111111111111",
            "actions": [
                {
                    "action": "TRANSFER",
                    "amount": "0.01",
                    "to": "0x1111111111111111111111111111111111111111",
                    "chain_id": 1,
                    "meta": {"asset": "ETH"},
                }
            ],
            "candidates": [
                {
                    "chain_id": 1,
                    "to": "0x1111111111111111111111111111111111111111",
                    "data": "0x",
                    "valueWei": "10000000000000000",
                    "meta": {"asset": "ETH"},
                }
            ],
        },
    ]
    user = (
        "Repair the plan using the judge issues and previous plan summary. "
        "Return ONLY JSON that matches the schema.\n"
        f"Examples: {json.dumps(examples, ensure_ascii=True)}\n"
        f"Input: {json.dumps(repair_input, ensure_ascii=True)}"
    )
    return {"system": REPAIR_PLAN_SYSTEM_PROMPT, "user": user}


def build_judge_prompt(judge_input: Dict[str, Any]) -> Dict[str, str]:
    examples = [
        {
            "verdict": "PASS",
            "reasoning_summary": "Plan, simulation, and policy checks are consistent.",
            "issues": [],
        },
        {
            "verdict": "NEEDS_REWORK",
            "reasoning_summary": "Simulation failed for one candidate; review required.",
            "issues": [
                {
                    "code": "SIMULATION_FAILED",
                    "severity": "HIGH",
                    "message": "Simulation failed for candidate 0.",
                    "data": {"index": 0},
                }
            ],
        },
    ]
    user = (
        "Evaluate the plan, simulation, and policy artifacts for consistency and safety. "
        "Return ONLY JSON that matches the schema.\n"
        f"Examples: {json.dumps(examples, ensure_ascii=True)}\n"
        f"Input: {json.dumps(judge_input, ensure_ascii=True)}"
    )
    return {"system": JUDGE_SYSTEM_PROMPT, "user": user}
