from __future__ import annotations

import json
from typing import Any, Dict


INTENT_CLASSIFIER_SYSTEM = (
    "You are a routing classifier for a crypto assistant. "
    "Return strict JSON only (no markdown). "
    "Required keys: mode, intent_type, confidence, slots, missing_slots, reason. "
    "mode must be one of QUERY, ACTION, CLARIFY, GENERAL. "
    "Use conversation history in context when available to fill missing slots. "
    "If the input is nonsense or random text, respond with mode GENERAL and low confidence. "
    "If context includes supported_tokens and the request uses unsupported tokens, "
    "return CLARIFY and ask for supported tokens."
)

CHAT_RESPONSE_SYSTEM = (
    "You are a helpful crypto assistant. "
    "Use the draft and context to produce a slightly more detailed and friendly reply. "
    "If mode is GENERAL, answer the user's question directly in 1-3 sentences; "
    "you may ignore the draft if it is not relevant. "
    "If the draft contains tool data (numbers, addresses), preserve those facts exactly "
    "and keep the line breaks. "
    "If mode is CLARIFY and context.reason is provided, include a short reason sentence. "
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
                "input": "1",
                "context": {
                    "history": [
                        {"role": "user", "content": "swap usdc to weth"},
                        {"role": "assistant", "content": "How much do you want to swap?"},
                    ]
                },
                "output": {
                    "mode": "ACTION",
                    "intent_type": "SWAP",
                    "confidence": 0.85,
                    "slots": {"amount_in": "1", "token_in": "USDC", "token_out": "WETH"},
                    "missing_slots": [],
                    "reason": "amount provided in follow-up",
                },
            },
            {
                "input": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
                "context": {
                    "history": [
                        {"role": "user", "content": "show my wallet snapshot"},
                        {"role": "assistant", "content": "What wallet address should I use?"},
                    ]
                },
                "output": {
                    "mode": "QUERY",
                    "intent_type": "WALLET_SNAPSHOT",
                    "confidence": 0.85,
                    "slots": {"wallet_address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"},
                    "missing_slots": [],
                    "reason": "wallet provided in follow-up",
                },
            },
            {
                "input": "mainnet",
                "context": {
                    "history": [
                        {"role": "user", "content": "what is my usdc balance"},
                        {"role": "assistant", "content": "Which chain are you using?"},
                    ]
                },
                "output": {
                    "mode": "QUERY",
                    "intent_type": "BALANCE",
                    "confidence": 0.8,
                    "slots": {"chain_id": 1, "token_symbol": "USDC"},
                    "missing_slots": [],
                    "reason": "chain provided in follow-up",
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
            {
                "input": "swaop sbfja to sjkhak",
                "output": {
                    "mode": "GENERAL",
                    "intent_type": "SMALLTALK",
                    "confidence": 0.2,
                    "slots": {},
                    "missing_slots": [],
                    "reason": "gibberish",
                },
            },
            {
                "input": "swap 1 dai to usdc",
                "context": {"supported_tokens": ["USDC", "WETH"]},
                "output": {
                    "mode": "CLARIFY",
                    "intent_type": "SWAP",
                    "confidence": 0.6,
                    "slots": {"token_in": "DAI", "token_out": "USDC", "amount_in": "1"},
                    "missing_slots": ["token_in"],
                    "reason": "unsupported_token",
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
