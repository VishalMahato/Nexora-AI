from __future__ import annotations

import json
from typing import Any, Dict


SYSTEM_PROMPT = (
    "You are Nexora planner. Output ONLY valid JSON matching the TxPlan schema. "
    "Do not include markdown or commentary. "
    "Schema requirements: "
    "plan_version (int, use 1), type ('noop' or 'plan'), reason (string or null), "
    "normalized_intent (string), actions (list), candidates (list). "
    "Action schemas: "
    "TRANSFER: {action:'TRANSFER', amount, to, chain_id, meta:{asset}}. "
    "APPROVE: {action:'APPROVE', token (symbol), spender (router key), amount}. "
    "SWAP: {action:'SWAP', token_in (symbol), token_out (symbol), amount_in, slippage_bps, "
    "recipient, router_key, deadline_seconds}. "
    "For SWAP, amount_in is a human-readable amount string (do NOT use base units). "
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
    "Action schemas: "
    "TRANSFER: {action:'TRANSFER', amount, to, chain_id, meta:{asset}}. "
    "APPROVE: {action:'APPROVE', token (symbol), spender (router key), amount}. "
    "SWAP: {action:'SWAP', token_in (symbol), token_out (symbol), amount_in, slippage_bps, "
    "recipient, router_key, deadline_seconds}. "
    "For SWAP, amount_in is a human-readable amount string (do NOT use base units). "
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

FINALIZE_SYSTEM_PROMPT = (
    "You are Nexora assistant. Write a user-facing response based on the finalize input. "
    "Do not mention internal terms like noop, needs_input, fatal_error, or simulation_success. "
    "If skipped_steps includes JUDGE_AGENT or SIMULATE_TXS, do not mention missing results. "
    "If final_status is NEEDS_INPUT, include the questions verbatim (bullet list is ok). "
    "If final_status is READY and tx_summary is present, explain the transaction in plain language, "
    "including token in/out, amount, slippage, and min receive if available. "
    "Include an estimated gas fee if provided and add a very brief explanation: "
    "'Gas is the network fee paid to process the transaction.' "
    "If approval_required is true, mention that an approval transaction is needed first. "
    "If final_status is BLOCKED/FAILED, give a brief reason and a next step. "
    "Keep it 3-6 sentences and helpful. "
    "Return ONLY valid JSON with keys: assistant_message (string), "
    "final_status_suggested ('READY'|'NEEDS_INPUT'|'BLOCKED'|'FAILED'|'NOOP'). "
    "No markdown or extra text."
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
        {
            "plan_version": 1,
            "type": "plan",
            "normalized_intent": "swap 20 usdc to eth",
            "actions": [
                {
                    "action": "APPROVE",
                    "token": "USDC",
                    "spender": "UNISWAP_V2_ROUTER",
                    "amount": "20",
                },
                {
                    "action": "SWAP",
                    "token_in": "USDC",
                    "token_out": "ETH",
                    "amount_in": "20",
                    "slippage_bps": 50,
                    "recipient": "0x1111111111111111111111111111111111111111",
                    "router_key": "UNISWAP_V2_ROUTER",
                    "deadline_seconds": 1200,
                },
            ],
            "candidates": [],
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


def build_finalize_prompt(finalize_input: Dict[str, Any]) -> Dict[str, str]:
    examples = [
        {
            "assistant_message": "I prepared a swap of 10 USDC to WETH. Slippage is 0.50% and the minimum you would receive is 0.0030 WETH. Estimated gas fee is ~0.0008 ETH; gas is the network fee paid to process the transaction. An approval transaction is required before the swap. Please review and approve to proceed.",
            "final_status_suggested": "READY",
        },
        {
            "assistant_message": "I need a bit more detail:\n- Which token are you swapping from?\n- How much do you want to swap?",
            "final_status_suggested": "NEEDS_INPUT",
        },
        {
            "assistant_message": "I can't proceed yet because the request is missing required details. Please share the amount and token you want to receive.",
            "final_status_suggested": "BLOCKED",
        },
        {
            "assistant_message": "I couldn't complete the request due to an error. Please try again or adjust the request.",
            "final_status_suggested": "FAILED",
        },
        {
            "assistant_message": "I couldn't identify an action to take. Tell me what you'd like to do, for example: 'swap 1 USDC to WETH'.",
            "final_status_suggested": "NOOP",
        },
    ]
    user = (
        "Compose the final assistant message based on the provided input. "
        "Return ONLY JSON that matches the schema.\n"
        f"Examples: {json.dumps(examples, ensure_ascii=True)}\n"
        f"Input: {json.dumps(finalize_input, ensure_ascii=True)}"
    )
    return {"system": FINALIZE_SYSTEM_PROMPT, "user": user}
