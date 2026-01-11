from __future__ import annotations

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse, IntentClassification, IntentMode
from app.chat.llm import classify_intent


_QUESTION_MAP = {
    "amount_in": "How much do you want to swap?",
    "token_in": "Which token are you swapping from?",
    "token_out": "Which token do you want to receive?",
    "wallet_address": "What wallet address should I use?",
    "chain_id": "Which chain are you using (e.g., Ethereum mainnet)?",
}


def _questions_for_missing_slots(missing_slots: list[str]) -> list[str]:
    questions = []
    for slot in missing_slots:
        question = _QUESTION_MAP.get(slot)
        if question:
            questions.append(question)
    if not questions:
        questions.append("Can you clarify what you want to do?")
    return questions


def route_chat(req: ChatRouteRequest) -> ChatRouteResponse:
    context = {
        "conversation_id": req.conversation_id,
        "wallet_address": req.wallet_address,
        "chain_id": req.chain_id,
        "metadata": req.metadata,
    }
    raw = classify_intent(req.message, context)
    try:
        classification = IntentClassification.model_validate(raw)
    except Exception:
        classification = IntentClassification(
            mode=IntentMode.CLARIFY,
            missing_slots=["clarification"],
            reason="invalid_classification",
        )

    if classification.mode == IntentMode.QUERY:
        return ChatRouteResponse(
            mode=IntentMode.QUERY,
            assistant_message="Got it - I can help with that.",
            questions=[],
            classification=classification,
        )

    if classification.mode == IntentMode.ACTION:
        return ChatRouteResponse(
            mode=IntentMode.ACTION,
            assistant_message="Got it - preparing that action.",
            questions=[],
            classification=classification,
        )

    questions = _questions_for_missing_slots(classification.missing_slots)
    return ChatRouteResponse(
        mode=IntentMode.CLARIFY,
        assistant_message="I need a bit more detail to proceed.",
        questions=questions,
        classification=classification,
    )
