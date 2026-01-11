from __future__ import annotations

from typing import Any, Dict

from app.config import get_settings
from app.chat.prompts import build_intent_classifier_prompt
from llm.client import LLMClient


def _fallback_classification(reason: str) -> Dict[str, Any]:
    return {
        "mode": "CLARIFY",
        "intent_type": None,
        "confidence": 0.0,
        "slots": {},
        "missing_slots": ["clarification"],
        "reason": reason,
    }


def classify_intent(message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.LLM_ENABLED:
        return _fallback_classification("llm_disabled")

    llm_client = LLMClient(
        model=settings.LLM_MODEL,
        provider=settings.LLM_PROVIDER,
        api_key=settings.OPENAI_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
        timeout_s=settings.LLM_TIMEOUT_S,
    )

    prompt = build_intent_classifier_prompt(message, context)
    try:
        raw_text = llm_client._call_provider(prompt=prompt)
        return llm_client._parse_json(raw_text)
    except Exception:
        return _fallback_classification("invalid_llm_output")
