from __future__ import annotations

from web3 import Web3

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse, IntentClassification, IntentMode
from app.chat.llm import classify_intent
from app.chat.tools import get_allowlists, get_token_balance, get_wallet_snapshot


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


def _requires_wallet_chain(intent_type: str) -> bool:
    return intent_type in {"BALANCE", "SNAPSHOT", "WALLET_SNAPSHOT", "ALLOWANCES"}


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
        intent = (classification.intent_type or "").upper()
        missing = []
        if _requires_wallet_chain(intent):
            if not req.wallet_address:
                missing.append("wallet_address")
            elif not Web3.is_address(req.wallet_address):
                missing.append("wallet_address")
            if not req.chain_id:
                missing.append("chain_id")
        if missing:
            clarify_classification = IntentClassification(
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
                confidence=classification.confidence,
                slots=classification.slots,
                missing_slots=missing,
                reason="missing_required_slots",
            )
            return ChatRouteResponse(
                mode=IntentMode.CLARIFY,
                assistant_message="I need a bit more detail to answer that.",
                questions=_questions_for_missing_slots(missing),
                classification=clarify_classification,
            )

        data = {}
        if intent == "ALLOWLISTS":
            chain_id = req.chain_id or 1
            data = {"allowlists": get_allowlists(chain_id)}
            assistant_message = "Here are the currently supported tokens and routers."
        elif intent in {"SNAPSHOT", "WALLET_SNAPSHOT"}:
            data = {"snapshot": get_wallet_snapshot(req.wallet_address, req.chain_id)}
            assistant_message = "Here is your wallet snapshot on this chain."
        else:
            token_symbol = classification.slots.get("token_symbol") if classification.slots else None
            if token_symbol:
                balance = get_token_balance(req.wallet_address, req.chain_id, str(token_symbol))
                data = {"balance": balance}
                assistant_message = f"Your {balance.get('symbol')} balance is {balance.get('balance')}."
            else:
                data = {"snapshot": get_wallet_snapshot(req.wallet_address, req.chain_id)}
                assistant_message = "Here is your wallet snapshot on this chain."

        return ChatRouteResponse(
            mode=IntentMode.QUERY,
            assistant_message=assistant_message,
            questions=[],
            data=data,
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
