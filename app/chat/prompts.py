from __future__ import annotations

import json
from typing import Any, Dict


INTENT_CLASSIFIER_SYSTEM = (
    "You are a routing classifier for a crypto assistant. "
    "Return strict JSON only (no markdown). "
    "Required keys: mode, intent_type, confidence, slots, missing_slots, reason. "
    "mode must be one of QUERY, ACTION, CLARIFY."
)


def build_intent_classifier_prompt(message: str, context: Dict[str, Any]) -> Dict[str, str]:
    user = {
        "message": message,
        "context": context,
        "examples": [
            {
                "input": "what's my balance?",
                "output": {
                    "mode": "QUERY",
                    "intent_type": "BALANCE",
                    "confidence": 0.9,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "wallet query",
                },
            },
            {
                "input": "what are the supported tokens?",
                "output": {
                    "mode": "QUERY",
                    "intent_type": "ALLOWLISTS",
                    "confidence": 0.8,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "config query",
                },
            },
            {
                "input": "swap usdc to weth",
                "output": {
                    "mode": "CLARIFY",
                    "intent_type": "SWAP",
                    "confidence": 0.7,
                    "slots": {"token_in": "USDC", "token_out": "WETH"},
                    "missing_slots": ["amount_in"],
                    "reason": "amount missing",
                },
            },
            {
                "input": "what is my usdc balance?",
                "output": {
                    "mode": "QUERY",
                    "intent_type": "BALANCE",
                    "confidence": 0.9,
                    "slots": {"token_symbol": "USDC"},
                    "missing_slots": [],
                    "reason": "token balance",
                },
            },
            {
                "input": "swap 1 usdc to weth",
                "output": {
                    "mode": "ACTION",
                    "intent_type": "SWAP",
                    "confidence": 0.9,
                    "slots": {"token_in": "USDC", "token_out": "WETH", "amount_in": "1"},
                    "missing_slots": [],
                    "reason": "actionable swap",
                },
            },
        ],
        "instruction": "Classify the message and return JSON only.",
    }

    return {
        "system": INTENT_CLASSIFIER_SYSTEM,
        "user": json.dumps(user, ensure_ascii=True),
    }
