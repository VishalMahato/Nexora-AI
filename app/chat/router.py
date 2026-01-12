from __future__ import annotations

import re

from sqlalchemy.orm import Session
from web3 import Web3

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse, IntentClassification, IntentMode
from app.chat.llm import classify_intent
from app.chat.runs_client import create_run_from_action, start_run_for_action
from app.chat.state_store import cleanup as cleanup_state
from app.chat.state_store import delete as delete_state
from app.chat.state_store import get as get_state
from app.chat.state_store import set as set_state
from app.chat.tools import get_allowlists, get_token_balance, get_wallet_snapshot
from app.config import get_settings


_QUESTION_MAP = {
    "amount_in": "How much do you want to swap?",
    "token_in": "Which token are you swapping from?",
    "token_out": "Which token do you want to receive?",
    "wallet_address": "What wallet address should I use?",
    "chain_id": "Which chain are you using (e.g., Ethereum mainnet)?",
}

_NUMBER_RE = re.compile(r"^\s*\d+(\.\d+)?\s*$")
_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_QUERY_INTENTS = {"BALANCE", "SNAPSHOT", "WALLET_SNAPSHOT", "ALLOWLISTS", "ALLOWANCES"}
_ACTION_INTENTS = {"SWAP", "TRANSFER", "APPROVE"}


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


def _resolve_wallet_chain(
    req: ChatRouteRequest,
    classification: IntentClassification | None,
    *,
    state: dict | None = None,
) -> tuple[str | None, int | None]:
    wallet = req.wallet_address
    chain_id = req.chain_id
    if state:
        wallet = wallet or state.get("wallet_address")
        chain_id = chain_id or state.get("chain_id")
    slots = classification.slots if classification else {}
    if not wallet:
        wallet = slots.get("wallet_address")
    if not chain_id:
        chain_id = slots.get("chain_id")
    if isinstance(chain_id, str) and chain_id.isdigit():
        chain_id = int(chain_id)
    return wallet, chain_id


def _missing_action_slots(
    intent_type: str,
    slots: dict[str, str],
    base_missing: list[str] | None,
) -> list[str]:
    missing = [slot for slot in (base_missing or []) if not slots.get(slot)]
    intent = intent_type.upper()
    if intent == "SWAP":
        if not slots.get("token_in"):
            missing.append("token_in")
        if not slots.get("token_out"):
            missing.append("token_out")
        if not slots.get("amount_in"):
            missing.append("amount_in")
    return list(dict.fromkeys(missing))


def _action_message_for_status(status: str | None) -> str:
    if status == "BLOCKED":
        return "I can't proceed: you don't have enough USDC. Try a smaller amount or use a wallet with USDC."
    if status == "FAILED":
        return "I can't proceed: the run failed. Review the timeline for details."
    return "Got it - I generated a safe transaction plan. Review and approve."


def _query_payload(
    intent: str,
    *,
    wallet_address: str | None,
    chain_id: int | None,
    slots: dict[str, str] | None,
) -> tuple[str, dict[str, str]]:
    data: dict[str, str] = {}
    if intent == "ALLOWLISTS":
        chain_id = chain_id or 1
        data = {"allowlists": get_allowlists(chain_id)}
        assistant_message = "Here are the currently supported tokens and routers."
    elif intent in {"SNAPSHOT", "WALLET_SNAPSHOT"}:
        data = {"snapshot": get_wallet_snapshot(wallet_address, chain_id)}
        assistant_message = "Here is your wallet snapshot on this chain."
    else:
        token_symbol = slots.get("token_symbol") if slots else None
        if token_symbol:
            balance = get_token_balance(wallet_address, chain_id, str(token_symbol))
            data = {"balance": balance}
            assistant_message = f"Your {balance.get('symbol')} balance is {balance.get('balance')}."
        else:
            data = {"snapshot": get_wallet_snapshot(wallet_address, chain_id)}
            assistant_message = "Here is your wallet snapshot on this chain."
    return assistant_message, data


def _fast_path_slots(message: str, missing_slots: list[str], *, chain_id: int | None) -> dict[str, str]:
    text = message.strip()
    lower = text.lower()
    slots: dict[str, str] = {}
    settings = get_settings()
    allowlisted = settings.allowlisted_tokens_for_chain(chain_id or 1)
    allowlisted_symbols = {k.upper() for k in allowlisted.keys()}

    if "amount_in" in missing_slots and _NUMBER_RE.match(text):
        slots["amount_in"] = text
    if "token_in" in missing_slots or "token_out" in missing_slots:
        for symbol in allowlisted_symbols:
            if symbol.lower() == lower:
                if "token_in" in missing_slots:
                    slots["token_in"] = symbol
                elif "token_out" in missing_slots:
                    slots["token_out"] = symbol
                break
    if "chain_id" in missing_slots and lower in {"1", "mainnet", "ethereum", "eth"}:
        slots["chain_id"] = "1"
    if "wallet_address" in missing_slots and _WALLET_RE.fullmatch(text):
        slots["wallet_address"] = text

    return slots


def _classification_from_state(
    *,
    intent_type: str,
    slots: dict[str, str],
    missing_slots: list[str],
    reason: str,
) -> IntentClassification:
    return IntentClassification(
        mode=IntentMode.CLARIFY,
        intent_type=intent_type,
        slots=slots,
        missing_slots=missing_slots,
        reason=reason,
    )


def route_chat(req: ChatRouteRequest, *, db: Session) -> ChatRouteResponse:
    cleanup_state()
    state = get_state(req.conversation_id) if req.conversation_id else None
    context = {
        "conversation_id": req.conversation_id,
        "wallet_address": req.wallet_address,
        "chain_id": req.chain_id,
        "metadata": req.metadata,
    }

    classification: IntentClassification | None = None

    if state and state.get("missing_slots"):
        missing_slots = list(state.get("missing_slots") or [])
        partial_slots = dict(state.get("partial_slots") or {})
        fast_slots = _fast_path_slots(req.message, missing_slots, chain_id=state.get("chain_id"))
        if fast_slots:
            partial_slots.update(fast_slots)
        else:
            raw = classify_intent(req.message, context)
            try:
                classification = IntentClassification.model_validate(raw)
            except Exception:
                classification = IntentClassification(
                    mode=IntentMode.CLARIFY,
                    missing_slots=["clarification"],
                    reason="invalid_classification",
                )
            if classification.slots:
                partial_slots.update(classification.slots)

        intent_type = (state.get("intent_type") or (classification.intent_type if classification else "") or "").upper()
        wallet_address, chain_id = _resolve_wallet_chain(req, classification, state=state)
        if intent_type in _QUERY_INTENTS:
            missing = []
            if _requires_wallet_chain(intent_type):
                if not wallet_address or not Web3.is_address(wallet_address):
                    missing.append("wallet_address")
                if not chain_id:
                    missing.append("chain_id")
            if missing:
                if req.conversation_id:
                    set_state(
                        req.conversation_id,
                        {
                            "intent_type": intent_type,
                            "intent_message": state.get("intent_message") or req.message,
                            "partial_slots": partial_slots,
                            "missing_slots": missing,
                            "wallet_address": wallet_address,
                            "chain_id": chain_id,
                        },
                    )
                return ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message="I need a bit more detail to proceed.",
                    questions=_questions_for_missing_slots(missing),
                    classification=classification
                    or _classification_from_state(
                        intent_type=intent_type,
                        slots=partial_slots,
                        missing_slots=missing,
                        reason="missing_required_slots",
                    ),
                    conversation_id=req.conversation_id,
                    pending=True,
                    pending_slots=partial_slots,
                )

            assistant_message, data = _query_payload(
                intent_type,
                wallet_address=wallet_address,
                chain_id=chain_id,
                slots=partial_slots,
            )
            return ChatRouteResponse(
                mode=IntentMode.QUERY,
                assistant_message=assistant_message,
                questions=[],
                data=data,
                classification=classification
                or _classification_from_state(
                    intent_type=intent_type,
                    slots=partial_slots,
                    missing_slots=[],
                    reason="followup_query",
                ),
                conversation_id=req.conversation_id,
                pending=False,
            )

        if intent_type in _ACTION_INTENTS:
            missing = _missing_action_slots(intent_type, partial_slots, state.get("missing_slots"))
            if not wallet_address or not Web3.is_address(wallet_address):
                missing.append("wallet_address")
            if not chain_id:
                missing.append("chain_id")
            missing = list(dict.fromkeys(missing))

            if missing:
                if req.conversation_id:
                    set_state(
                        req.conversation_id,
                        {
                            "intent_type": intent_type,
                            "intent_message": state.get("intent_message") or req.message,
                            "partial_slots": partial_slots,
                            "missing_slots": missing,
                            "wallet_address": wallet_address,
                            "chain_id": chain_id,
                        },
                    )
                return ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message="I need a bit more detail to proceed.",
                    questions=_questions_for_missing_slots(missing),
                    classification=classification
                    or _classification_from_state(
                        intent_type=intent_type,
                        slots=partial_slots,
                        missing_slots=missing,
                        reason="missing_required_slots",
                    ),
                    conversation_id=req.conversation_id,
                    pending=True,
                    pending_slots=partial_slots,
                )

            intent_message = state.get("intent_message") or req.message
            run_id = create_run_from_action(
                db=db,
                intent=intent_message,
                wallet_address=wallet_address,
                chain_id=int(chain_id),
            )
            run_result = start_run_for_action(db=db, run_id=run_id)
            run_status = run_result.get("status")
            fetch_url = f"/v1/runs/{run_id}?includeArtifacts=true"
            if req.conversation_id:
                delete_state(req.conversation_id)

            return ChatRouteResponse(
                mode=IntentMode.ACTION,
                assistant_message=_action_message_for_status(run_status),
                questions=[],
                run_id=str(run_id),
                run_ref={"id": str(run_id), "status": run_status, "fetch_url": fetch_url},
                next_ui="SHOW_APPROVAL_SCREEN" if run_status == "AWAITING_APPROVAL" else None,
                classification=classification,
                conversation_id=req.conversation_id,
            )

        return ChatRouteResponse(
            mode=IntentMode.CLARIFY,
            assistant_message="I need a bit more detail to proceed.",
            questions=_questions_for_missing_slots(missing_slots),
            classification=classification
            or _classification_from_state(
                intent_type=intent_type,
                slots=partial_slots,
                missing_slots=missing_slots,
                reason="missing_required_slots",
            ),
            conversation_id=req.conversation_id,
            pending=True,
            pending_slots=partial_slots,
        )

    if classification is None:
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
                conversation_id=req.conversation_id,
                pending=False,
            )

        assistant_message, data = _query_payload(
            intent,
            wallet_address=req.wallet_address,
            chain_id=req.chain_id,
            slots=classification.slots or {},
        )

        return ChatRouteResponse(
            mode=IntentMode.QUERY,
            assistant_message=assistant_message,
            questions=[],
            data=data,
            classification=classification,
            conversation_id=req.conversation_id,
            pending=False,
        )

    if classification.mode == IntentMode.ACTION:
        wallet_address, chain_id = _resolve_wallet_chain(req, classification)
        missing = _missing_action_slots(
            classification.intent_type or "",
            classification.slots or {},
            classification.missing_slots,
        )
        if not wallet_address or not Web3.is_address(wallet_address):
            missing.append("wallet_address")
        if not chain_id:
            missing.append("chain_id")
        missing = list(dict.fromkeys(missing))
        if missing:
            clarify_classification = IntentClassification(
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
                confidence=classification.confidence,
                slots=classification.slots,
                missing_slots=missing,
                reason="missing_required_slots",
            )
            if req.conversation_id:
                set_state(
                    req.conversation_id,
                    {
                        "intent_type": (classification.intent_type or "").upper(),
                        "intent_message": req.message,
                        "partial_slots": classification.slots or {},
                        "missing_slots": missing,
                        "wallet_address": wallet_address,
                        "chain_id": chain_id,
                    },
                )
            return ChatRouteResponse(
                mode=IntentMode.CLARIFY,
                assistant_message="I need a bit more detail to proceed.",
                questions=_questions_for_missing_slots(missing),
                classification=clarify_classification,
                conversation_id=req.conversation_id,
                pending=True,
                pending_slots=classification.slots or {},
            )

        run_id = create_run_from_action(
            db=db,
            intent=req.message,
            wallet_address=wallet_address,
            chain_id=int(chain_id),
        )
        run_result = start_run_for_action(db=db, run_id=run_id)
        run_status = run_result.get("status")
        fetch_url = f"/v1/runs/{run_id}?includeArtifacts=true"
        if req.conversation_id:
            delete_state(req.conversation_id)

        return ChatRouteResponse(
            mode=IntentMode.ACTION,
            assistant_message=_action_message_for_status(run_status),
            questions=[],
            run_id=str(run_id),
            run_ref={"id": str(run_id), "status": run_status, "fetch_url": fetch_url},
            next_ui="SHOW_APPROVAL_SCREEN" if run_status == "AWAITING_APPROVAL" else None,
            classification=classification,
            conversation_id=req.conversation_id,
        )

    questions = _questions_for_missing_slots(classification.missing_slots)
    if req.conversation_id:
        set_state(
            req.conversation_id,
            {
                "intent_type": (classification.intent_type or "").upper(),
                "intent_message": req.message,
                "partial_slots": classification.slots or {},
                "missing_slots": classification.missing_slots or [],
                "wallet_address": req.wallet_address,
                "chain_id": req.chain_id,
            },
        )
    return ChatRouteResponse(
        mode=IntentMode.CLARIFY,
        assistant_message="I need a bit more detail to proceed.",
        questions=questions,
        classification=classification,
        conversation_id=req.conversation_id,
        pending=bool(req.conversation_id),
        pending_slots=classification.slots or {},
    )
