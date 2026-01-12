from __future__ import annotations

import json
from typing import Any, Dict


INTENT_CLASSIFIER_SYSTEM = (
    "You are a routing classifier for a crypto assistant. "
    "Return strict JSON only (no markdown). "
    "Required keys: mode, intent_type, confidence, slots, missing_slots, reason. "
    "mode must be one of QUERY, ACTION, CLARIFY, GENERAL. "
    "Use conversation history in context when available to fill missing slots."
)

CHAT_RESPONSE_SYSTEM = (
    "You are a helpful crypto assistant. "
    "Use the draft and context to produce a slightly more detailed and friendly reply. "
    "If mode is GENERAL, answer the user's question directly in 1-3 sentences; "
    "you may ignore the draft if it is not relevant. "
    "If the draft contains tool data (numbers, addresses), preserve those facts exactly "
    "and keep the line breaks. "
    "If the draft contains questions, keep those questions verbatim. "
    "Do not invent new facts. "
    "Return strict JSON only with a single key: message."
)


def build_intent_classifier_prompt(message: str, context: Dict[str, Any]) -> Dict[str, str]:
    user = {
        "message": message,
        "context": context,
        "examples": [
            {
                "input": "hi there",
                "output": {
                    "mode": "GENERAL",
                    "intent_type": "SMALLTALK",
                    "confidence": 0.9,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "greeting",
                },
            },
            {
                "input": "what can you do?",
                "output": {
                    "mode": "GENERAL",
                    "intent_type": "HELP",
                    "confidence": 0.9,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "capabilities request",
                },
            },
            {
                "input": "thanks",
                "output": {
                    "mode": "GENERAL",
                    "intent_type": "SMALLTALK",
                    "confidence": 0.8,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "gratitude",
                },
            },
            {
                "input": "ok",
                "output": {
                    "mode": "GENERAL",
                    "intent_type": "SMALLTALK",
                    "confidence": 0.7,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "acknowledgement",
                },
            },
            {
                "input": "what is chain?",
                "output": {
                    "mode": "GENERAL",
                    "intent_type": "HELP",
                    "confidence": 0.8,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "concept question",
                },
            },
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


def build_chat_response_prompt(draft: str, context: Dict[str, Any]) -> Dict[str, str]:
    user = {
        "draft": draft,
        "context": context,
        "instruction": "Return JSON: {\"message\": \"...\"}",
    }
    return {
        "system": CHAT_RESPONSE_SYSTEM,
        "user": json.dumps(user, ensure_ascii=True),
    }
