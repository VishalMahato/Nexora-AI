from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session
from web3 import Web3

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse, IntentClassification, IntentMode
from app.chat.llm import classify_intent, polish_assistant_message
from app.chat.runs_client import create_run_from_action, start_run_for_action
from app.chat.state_store import cleanup as cleanup_state
from app.chat.state_store import delete as delete_state
from app.chat.state_store import get as get_state
from app.chat.state_store import set as set_state
from app.chat.tools import get_allowlists, get_token_balance, get_wallet_snapshot
from app.config import get_settings
from chain.chains import UnsupportedChainError, list_supported_chains
from chain.rpc import Web3RPCError

_QUESTION_MAP = {
    "amount_in": "How much do you want to swap?",
    "token_in": "Which token are you swapping from?",
    "token_out": "Which token do you want to receive?",
    "token_symbol": "Which token should I use?",
    "token": "Which token should I use?",
    "wallet_address": "What wallet address should I use?",
    "chain_id": "Which chain are you using (e.g., Ethereum mainnet)?",
}

_QUERY_INTENTS = {"BALANCE", "SNAPSHOT", "WALLET_SNAPSHOT", "ALLOWLISTS", "ALLOWANCES"}
_ACTION_INTENTS = {"SWAP", "TRANSFER", "APPROVE"}
_GENERAL_SUGGESTIONS = [
    "Check supported tokens",
    "Show wallet snapshot",
    "Swap USDC to WETH",
    "Check USDC balance",
]

_ACTION_KEYWORDS = {"swap", "trade", "send", "transfer", "approve", "buy", "sell", "move"}

logger = logging.getLogger(__name__)


def _short_address(value: str | None) -> str:
    if not value or not isinstance(value, str):
        return "unknown"
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _format_decimal(amount_str: str | None, decimals: int | None) -> str:
    if amount_str is None or decimals is None:
        return "unknown"
    try:
        if not isinstance(amount_str, str):
            amount_str = str(amount_str)
        raw = int(amount_str)
    except (ValueError, TypeError):
        return "unknown"
    if decimals <= 0:
        return str(raw)
    scale = 10 ** decimals
    whole = raw // scale
    frac = raw % scale
    frac_str = str(frac).rjust(decimals, "0").rstrip("0")
    if not frac_str:
        return str(whole)
    return f"{whole}.{frac_str[:4]}"


def _format_allowlists(allowlists: dict[str, Any]) -> str:
    tokens = allowlists.get("tokens") or {}
    routers = allowlists.get("routers") or {}
    token_names = ", ".join(sorted(tokens.keys())) if tokens else "none"
    router_names = ", ".join(sorted(routers.keys())) if routers else "none"
    chain_id = allowlists.get("chain_id")
    return (
        "Here are the currently supported tokens and routers."
        f"\nChain: {chain_id if chain_id is not None else 'unknown'}"
        f"\nTokens: {token_names}"
        f"\nRouters: {router_names}"
    )


def _format_wallet_snapshot(snapshot: dict[str, Any]) -> str:
    chain_id = snapshot.get("chainId")
    wallet_full = snapshot.get("walletAddress") or "unknown"
    native = snapshot.get("native") or {}
    native_balance = _format_decimal(native.get("balanceWei"), 18)

    lines = [
        "Wallet snapshot",
        f"Chain: {chain_id if chain_id is not None else 'unknown'}",
        f"Wallet: {wallet_full}",
        f"Native: {native_balance} ETH",
    ]

    tokens = snapshot.get("erc20") or []
    if tokens:
        lines.append("Tokens:")
        for token in tokens[:8]:
            symbol = token.get("symbol") or "UNKNOWN"
            balance = _format_decimal(token.get("balance"), token.get("decimals"))
            lines.append(f"- {symbol}: {balance}")

    allowances = snapshot.get("allowances") or []
    if allowances:
        lines.append("Allowances:")
        for item in allowances[:6]:
            token = item.get("token") or "unknown"
            spender = item.get("spender") or "unknown"
            allowance = item.get("allowance")
            lines.append(f"- {token} -> {spender}: {allowance}")

    return "\n".join(lines)


def _format_token_balance(balance: dict[str, Any]) -> str:
    symbol = balance.get("symbol") or "UNKNOWN"
    value = _format_decimal(balance.get("balance"), balance.get("decimals"))
    if value == "unknown":
        return f"I couldn't find a balance for {symbol}."
    return f"Your {symbol} balance is {value}."


def _questions_for_missing_slots(missing_slots: list[str]) -> list[str]:
    questions = []
    for slot in missing_slots:
        question = _QUESTION_MAP.get(slot)
        if question:
            questions.append(question)
    if not questions:
        questions.append("Can you clarify what you want to do?")
    return questions


def _clarify_message(missing_slots: list[str], *, intro: str | None = None) -> str:
    questions = _questions_for_missing_slots(missing_slots)
    if len(questions) == 1:
        message = questions[0]
    else:
        message = "I need a bit more detail:\n" + "\n".join(f"- {q}" for q in questions)
    if intro:
        return f"{intro} {message}"
    return message


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


def _supported_action_tokens(chain_id: int | None) -> set[str]:
    settings = get_settings()
    tokens = settings.allowlisted_tokens_for_chain(chain_id)
    if not tokens:
        return set()
    supported: set[str] = set()
    for symbol, meta in tokens.items():
        if isinstance(meta, dict) and meta.get("is_native"):
            continue
        supported.add(str(symbol).upper())
    return supported


def _extract_action_tokens(slots: dict[str, str] | None) -> set[str]:
    if not slots:
        return set()
    tokens: set[str] = set()
    for key in ("token_in", "token_out", "token_symbol", "token", "asset"):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            tokens.add(value.strip().upper())
    return tokens


def _message_mentions_supported_token(message: str, supported_tokens: set[str]) -> bool:
    if not supported_tokens or not message:
        return False
    text = message.upper()
    for token in supported_tokens:
        if re.search(rf"\\b{re.escape(token)}\\b", text):
            return True
    return False


def _has_action_keyword(message: str) -> bool:
    if not message:
        return False
    text = message.lower()
    return any(keyword in text for keyword in _ACTION_KEYWORDS)


def _gibberish_score(message: str, *, min_len: int) -> float:
    text = (message or "").strip()
    if not text:
        return 1.0
    if Web3.is_address(text):
        return 0.0
    if re.fullmatch(r"\\d+(\\.\\d+)?", text):
        return 0.0

    letters = sum(1 for c in text if c.isalpha())
    alnum = sum(1 for c in text if c.isalnum())
    vowels = sum(1 for c in text if c.lower() in "aeiou")

    score = 0.0
    if len(text) < min_len:
        score += 0.35
    alpha_ratio = letters / alnum if alnum else 0.0
    if alpha_ratio < 0.3:
        score += 0.35
    vowel_ratio = vowels / letters if letters else 0.0
    if letters and vowel_ratio < 0.2:
        score += 0.3
    if re.search(r"(.)\\1\\1\\1", text):
        score += 0.35

    tokens = re.findall(r"[A-Za-z]{4,}", text)
    if tokens:
        no_vowel = sum(1 for token in tokens if not any(ch in "aeiouAEIOU" for ch in token))
        if no_vowel / len(tokens) > 0.6:
            score += 0.3

    return min(score, 1.0)


def _is_gibberish(message: str, *, settings) -> bool:
    score = _gibberish_score(message, min_len=settings.chat_min_message_len)
    return score >= settings.chat_gibberish_score_max


def _should_block_action_message(
    message: str,
    *,
    confidence: float | None,
    supported_tokens: set[str],
    settings,
) -> bool:
    if confidence is not None and confidence < settings.chat_min_confidence:
        return True
    signal_ok = _has_action_keyword(message) or _message_mentions_supported_token(
        message, supported_tokens
    )
    if not signal_ok:
        return True
    if _is_gibberish(message, settings=settings) and not _has_action_keyword(message):
        return True
    return False


def _unsupported_token_message(supported_tokens: set[str]) -> str:
    if not supported_tokens:
        return "This action is not supported yet. Please try a supported token."
    supported_list = ", ".join(sorted(supported_tokens))
    return f"We currently support {supported_list} only. Which token should I use?"


def _unsupported_token_missing_slots(intent_type: str | None) -> list[str]:
    intent = (intent_type or "").upper()
    if intent == "SWAP":
        return ["token_in", "token_out"]
    if intent in {"TRANSFER", "APPROVE"}:
        return ["token_symbol"]
    return ["token"]


def _unsupported_chain_message(chain_id: int | None) -> str:
    supported = list_supported_chains()
    if supported:
        supported_list = ", ".join(str(cid) for cid in supported)
        return f"Unsupported chain_id {chain_id}. Supported chains: {supported_list}."
    return f"Unsupported chain_id {chain_id}. Please provide a supported chain."


def _rpc_unavailable_message(chain_id: int | None) -> str:
    return (
        f"Unable to reach the RPC for chain_id {chain_id}. "
        "Please try again or switch to a different RPC endpoint."
    )


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
        amount = slots.get("amount_in") or slots.get("amount")
        if not amount:
            missing.append("amount_in")
    return list(dict.fromkeys(missing))


def _build_intent_from_slots(intent_type: str, slots: dict[str, str]) -> str | None:
    intent = intent_type.upper()
    if intent == "SWAP":
        amount = slots.get("amount_in") or slots.get("amount")
        token_in = slots.get("token_in")
        token_out = slots.get("token_out")
        if amount and token_in and token_out:
            return f"swap {amount} {token_in} to {token_out}"
    return None


def _extract_block_reason(artifacts: dict[str, Any] | None) -> str | None:
    if not artifacts:
        return None
    decision = artifacts.get("decision") or {}
    reasons = decision.get("reasons") or []
    for reason in reasons:
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    judge_issues = ((artifacts.get("judge_result") or {}).get("output") or {}).get("issues") or []
    if isinstance(judge_issues, list) and judge_issues:
        issue = judge_issues[0] or {}
        if isinstance(issue, dict):
            message = issue.get("message") or issue.get("code")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return None


def _action_message_for_status(status: str | None, *, artifacts: dict[str, Any] | None = None) -> str:
    if status == "CREATED":
        return "Got it — I'm starting the run now and will stream updates as each step completes."
    if status == "BLOCKED":
        reason = _extract_block_reason(artifacts)
        if reason:
            return f"I can't proceed: {reason}"
        return "I can't proceed: the run was blocked by safety checks. Review the timeline for details."
    if status == "FAILED":
        return "I can't proceed: the run failed. Review the timeline for details."
    return "Got it - I generated a safe transaction plan. Review and approve."


def _query_payload(
    intent: str,
    *,
    wallet_address: str | None,
    chain_id: int | None,
    slots: dict[str, str] | None,
) -> tuple[str, dict[str, Any]]:
    data: dict[str, Any] = {}

    if intent == "ALLOWLISTS":
        chain_id = chain_id or 1
        allowlists = get_allowlists(chain_id)
        data = {"allowlists": allowlists}
        assistant_message = _format_allowlists(allowlists)

    elif intent in {"SNAPSHOT", "WALLET_SNAPSHOT", "BALANCE"}:
        snapshot = get_wallet_snapshot(wallet_address, chain_id)
        data = {"snapshot": snapshot}
        assistant_message = _format_wallet_snapshot(snapshot)

    else:
        token_symbol = slots.get("token_symbol") if slots else None
        if token_symbol:
            balance = get_token_balance(wallet_address, chain_id, str(token_symbol))
            data = {"balance": balance}
            assistant_message = _format_token_balance(balance)
        else:
            snapshot = get_wallet_snapshot(wallet_address, chain_id)
            data = {"snapshot": snapshot}
            assistant_message = _format_wallet_snapshot(snapshot)

    return assistant_message, data


def _fast_path_slots(message: str, missing_slots: list[str], *, chain_id: int | None) -> dict[str, str]:
    return {}


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


def _should_interrupt_pending(
    *,
    state_intent: str,
    classification: IntentClassification | None,
    fast_slots: dict[str, str],
) -> bool:
    if fast_slots:
        return False
    if not classification:
        return False
    if classification.mode == IntentMode.GENERAL:
        return False
    if classification.mode == IntentMode.QUERY:
        return False
    incoming_intent = (classification.intent_type or "").upper()
    if incoming_intent and state_intent and incoming_intent != state_intent:
        return True
    return False


def _general_payload() -> tuple[str, dict[str, Any], list[str]]:
    return (
        "Hi! I can help with swaps, wallet snapshots, and balances. What would you like to do?",
        {},
        list(_GENERAL_SUGGESTIONS),
    )


def _finalize_response(
    resp: ChatRouteResponse,
    *,
    req: ChatRouteRequest,
    mode: IntentMode | None = None,
    intent_type: str | None = None,
    status: str | None = None,
) -> ChatRouteResponse:
    mode_value = mode or resp.mode
    mode_str = mode_value.value if isinstance(mode_value, IntentMode) else str(mode_value)
    resolved_intent = intent_type
    if not resolved_intent and resp.classification:
        resolved_intent = resp.classification.intent_type
    context = {
        "mode": mode_str,
        "intent_type": resolved_intent,
        "user_message": req.message,
        "status": status,
    }
    if resp.classification:
        context["reason"] = resp.classification.reason
        context["missing_slots"] = resp.classification.missing_slots
    if resp.questions:
        context["questions"] = resp.questions
    resp.assistant_message = polish_assistant_message(resp.assistant_message, context=context)
    return resp


def _route_from_classification(
    req: ChatRouteRequest,
    *,
    db: Session,
    classification: IntentClassification,
) -> ChatRouteResponse:
    defer_start = bool((req.metadata or {}).get("defer_start"))
    if classification.mode == IntentMode.QUERY:
        intent = (classification.intent_type or "").upper()
        if not intent:
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message=_clarify_message(["clarification"]),
                    questions=["What would you like to check?"],
                    classification=IntentClassification(
                        mode=IntentMode.CLARIFY,
                        intent_type=None,
                        confidence=classification.confidence,
                        slots=classification.slots,
                        missing_slots=["clarification"],
                        reason="missing_intent_type",
                    ),
                    conversation_id=req.conversation_id,
                    pending=False,
                ),
                req=req,
                mode=IntentMode.CLARIFY,
            )
        missing: list[str] = []

        if _requires_wallet_chain(intent):
            if not req.wallet_address or not Web3.is_address(req.wallet_address):
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
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message=_clarify_message(missing),
                    questions=_questions_for_missing_slots(missing),
                    classification=clarify_classification,
                    conversation_id=req.conversation_id,
                    pending=False,
                ),
                req=req,
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
            )

        try:
            assistant_message, data = _query_payload(
                intent,
                wallet_address=req.wallet_address,
                chain_id=req.chain_id,
                slots=classification.slots or {},
            )
        except UnsupportedChainError:
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message=_unsupported_chain_message(req.chain_id),
                    questions=_questions_for_missing_slots(["chain_id"]),
                    classification=IntentClassification(
                        mode=IntentMode.CLARIFY,
                        intent_type=classification.intent_type,
                        confidence=classification.confidence,
                        slots=classification.slots,
                        missing_slots=["chain_id"],
                        reason="unsupported_chain",
                    ),
                    conversation_id=req.conversation_id,
                    pending=False,
                ),
                req=req,
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
            )
        except Web3RPCError:
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message=_rpc_unavailable_message(req.chain_id),
                    questions=_questions_for_missing_slots(["chain_id"]),
                    classification=IntentClassification(
                        mode=IntentMode.CLARIFY,
                        intent_type=classification.intent_type,
                        confidence=classification.confidence,
                        slots=classification.slots,
                        missing_slots=["chain_id"],
                        reason="rpc_unavailable",
                    ),
                    conversation_id=req.conversation_id,
                    pending=False,
                ),
                req=req,
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
            )
        if req.conversation_id:
            delete_state(req.conversation_id)

        return _finalize_response(
            ChatRouteResponse(
                mode=IntentMode.QUERY,
                assistant_message=assistant_message,
                questions=[],
                data=data,
                classification=classification,
                conversation_id=req.conversation_id,
                pending=False,
            ),
            req=req,
            mode=IntentMode.QUERY,
            intent_type=intent,
        )

    if classification.mode == IntentMode.GENERAL:
        assistant_message, data, suggestions = _general_payload()
        return _finalize_response(
            ChatRouteResponse(
                mode=IntentMode.GENERAL,
                assistant_message=assistant_message,
                questions=[],
                data=data,
                suggestions=suggestions,
                classification=classification,
                conversation_id=req.conversation_id,
                pending=False,
            ),
            req=req,
            mode=IntentMode.GENERAL,
            intent_type=classification.intent_type,
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
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message=_clarify_message(missing),
                    questions=_questions_for_missing_slots(missing),
                    classification=clarify_classification,
                    conversation_id=req.conversation_id,
                    pending=True,
                    pending_slots=classification.slots or {},
                ),
                req=req,
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
            )

        settings = get_settings()
        supported_tokens = _supported_action_tokens(chain_id)
        tokens = _extract_action_tokens(classification.slots or {})
        unsupported = tokens - supported_tokens if supported_tokens else set()
        if unsupported:
            missing_tokens = _unsupported_token_missing_slots(classification.intent_type)
            clarify_classification = IntentClassification(
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
                confidence=classification.confidence,
                slots=classification.slots,
                missing_slots=missing_tokens,
                reason="unsupported_token",
            )
            if req.conversation_id:
                set_state(
                    req.conversation_id,
                    {
                        "intent_type": (classification.intent_type or "").upper(),
                        "intent_message": req.message,
                        "partial_slots": classification.slots or {},
                        "missing_slots": missing_tokens,
                        "wallet_address": wallet_address,
                        "chain_id": chain_id,
                    },
                )
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.CLARIFY,
                    assistant_message=_unsupported_token_message(supported_tokens),
                    questions=_questions_for_missing_slots(missing_tokens),
                    classification=clarify_classification,
                    conversation_id=req.conversation_id,
                    pending=True,
                    pending_slots=classification.slots or {},
                ),
                req=req,
                mode=IntentMode.CLARIFY,
                intent_type=classification.intent_type,
            )

        intent_message = _build_intent_from_slots(
            classification.intent_type or "",
            classification.slots or {},
        ) or req.message
        if _should_block_action_message(
            req.message,
            confidence=classification.confidence,
            supported_tokens=supported_tokens,
            settings=settings,
        ):
            logger.info("router_guard: blocked action intent", extra={"reason": "low_signal"})
            assistant_message, data, suggestions = _general_payload()
            assistant_message = "I didn't catch that. Could you rephrase what you want to do?"
            downgraded = classification.model_copy(
                update={"mode": IntentMode.GENERAL, "reason": "low_signal_or_gibberish"}
            )
            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.GENERAL,
                    assistant_message=assistant_message,
                    questions=[],
                    data=data,
                    suggestions=suggestions,
                    classification=downgraded,
                    conversation_id=req.conversation_id,
                    pending=False,
                ),
                req=req,
                mode=IntentMode.GENERAL,
                intent_type=classification.intent_type,
            )

        run_id = create_run_from_action(
            db=db,
            intent=intent_message,
            wallet_address=wallet_address,
            chain_id=int(chain_id),
        )
        run_result: dict[str, Any] = {}
        run_status = "CREATED"
        if not defer_start:
            run_result = start_run_for_action(db=db, run_id=run_id)
            run_status = run_result.get("status")
        fetch_url = f"/v1/runs/{run_id}?includeArtifacts=true"

        if req.conversation_id:
            delete_state(req.conversation_id)

        return _finalize_response(
            ChatRouteResponse(
                mode=IntentMode.ACTION,
                assistant_message=_action_message_for_status(
                    run_status,
                    artifacts=run_result.get("artifacts"),
                ),
                questions=[],
                run_id=str(run_id),
                run_ref={"id": str(run_id), "status": run_status, "fetch_url": fetch_url},
                next_ui="SHOW_APPROVAL_SCREEN" if run_status == "AWAITING_APPROVAL" else None,
                classification=classification,
                conversation_id=req.conversation_id,
            ),
            req=req,
            mode=IntentMode.ACTION,
            intent_type=classification.intent_type,
            status=run_status,
        )

    questions = _questions_for_missing_slots(classification.missing_slots)
    should_store = bool(
        req.conversation_id
        and ((classification.intent_type or "").strip() or (classification.slots or {}))
    )
    if should_store:
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
    return _finalize_response(
        ChatRouteResponse(
            mode=IntentMode.CLARIFY,
            assistant_message=_clarify_message(classification.missing_slots),
            questions=questions,
            classification=classification,
            conversation_id=req.conversation_id,
            pending=should_store,
            pending_slots=classification.slots or {},
        ),
        req=req,
        mode=IntentMode.CLARIFY,
        intent_type=classification.intent_type,
    )


def _normalize_classification(classification: IntentClassification) -> IntentClassification:
    intent = (classification.intent_type or "").upper()
    if intent in _QUERY_INTENTS and classification.mode != IntentMode.QUERY:
        return classification.model_copy(update={"mode": IntentMode.QUERY})
    if intent in _ACTION_INTENTS and classification.mode == IntentMode.QUERY:
        return classification.model_copy(update={"mode": IntentMode.ACTION})
    return classification


def route_chat(req: ChatRouteRequest, *, db: Session) -> ChatRouteResponse:
    cleanup_state()
    settings = get_settings()
    if settings.demo_mode and settings.demo_wallet_address:
        updates = {"wallet_address": settings.demo_wallet_address}
        if settings.demo_chain_id is not None:
            updates["chain_id"] = settings.demo_chain_id
        req = req.model_copy(update=updates)
    defer_start = bool((req.metadata or {}).get("defer_start"))
    state = get_state(req.conversation_id) if req.conversation_id else None
    if state and (not state.get("missing_slots") or (not state.get("intent_type") and not state.get("partial_slots"))):
        if req.conversation_id:
            delete_state(req.conversation_id)
        state = None

    context = {
        "conversation_id": req.conversation_id,
        "wallet_address": req.wallet_address,
        "chain_id": req.chain_id,
        "metadata": req.metadata,
    }
    if req.chain_id:
        context["supported_tokens"] = sorted(_supported_action_tokens(req.chain_id))
    if req.metadata and isinstance(req.metadata, dict):
        history = req.metadata.get("history")
        if isinstance(history, list):
            context["history"] = history

    classification: IntentClassification | None = None

    # Follow-up path (pending conversation)
    if state and state.get("missing_slots"):
        missing_slots = list(state.get("missing_slots") or [])
        partial_slots = dict(state.get("partial_slots") or {})
        context["pending_intent"] = state.get("intent_type")
        context["pending_missing_slots"] = missing_slots

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
            classification = _normalize_classification(classification)
            if classification.mode == IntentMode.GENERAL:
                assistant_message, data, suggestions = _general_payload()
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.GENERAL,
                        assistant_message=assistant_message,
                        questions=[],
                        data=data,
                        suggestions=suggestions,
                        classification=classification,
                        conversation_id=req.conversation_id,
                        pending=True,
                        pending_slots=partial_slots,
                    ),
                    req=req,
                    mode=IntentMode.GENERAL,
                    intent_type=classification.intent_type,
                )
            if classification.mode == IntentMode.QUERY:
                wallet_address, chain_id = _resolve_wallet_chain(req, classification, state=state)
                intent = (classification.intent_type or "").upper()
                if not intent:
                    return _finalize_response(
                        ChatRouteResponse(
                            mode=IntentMode.CLARIFY,
                            assistant_message=_clarify_message(["clarification"]),
                            questions=["What would you like to check?"],
                            classification=IntentClassification(
                                mode=IntentMode.CLARIFY,
                                intent_type=None,
                                confidence=classification.confidence,
                                slots=classification.slots,
                                missing_slots=["clarification"],
                                reason="missing_intent_type",
                            ),
                            conversation_id=req.conversation_id,
                            pending=True,
                            pending_slots=partial_slots,
                        ),
                        req=req,
                        mode=IntentMode.CLARIFY,
                    )
                missing: list[str] = []
                if _requires_wallet_chain(intent):
                    if not wallet_address or not Web3.is_address(wallet_address):
                        missing.append("wallet_address")
                    if not chain_id:
                        missing.append("chain_id")

                if missing:
                    return _finalize_response(
                        ChatRouteResponse(
                            mode=IntentMode.CLARIFY,
                            assistant_message=_clarify_message(missing),
                            questions=_questions_for_missing_slots(missing),
                            classification=IntentClassification(
                                mode=IntentMode.CLARIFY,
                                intent_type=classification.intent_type,
                                confidence=classification.confidence,
                                slots=classification.slots,
                                missing_slots=missing,
                                reason="missing_required_slots",
                            ),
                            conversation_id=req.conversation_id,
                            pending=True,
                            pending_slots=partial_slots,
                        ),
                        req=req,
                        mode=IntentMode.CLARIFY,
                        intent_type=classification.intent_type,
                    )

                try:
                    assistant_message, data = _query_payload(
                        intent,
                        wallet_address=wallet_address,
                        chain_id=chain_id,
                        slots=classification.slots or {},
                    )
                except UnsupportedChainError:
                    return _finalize_response(
                        ChatRouteResponse(
                            mode=IntentMode.CLARIFY,
                            assistant_message=_unsupported_chain_message(chain_id),
                            questions=_questions_for_missing_slots(["chain_id"]),
                            classification=IntentClassification(
                                mode=IntentMode.CLARIFY,
                                intent_type=classification.intent_type,
                                confidence=classification.confidence,
                                slots=classification.slots,
                                missing_slots=["chain_id"],
                                reason="unsupported_chain",
                            ),
                            conversation_id=req.conversation_id,
                            pending=True,
                            pending_slots=partial_slots,
                        ),
                        req=req,
                        mode=IntentMode.CLARIFY,
                        intent_type=classification.intent_type,
                    )
                except Web3RPCError:
                    return _finalize_response(
                        ChatRouteResponse(
                            mode=IntentMode.CLARIFY,
                            assistant_message=_rpc_unavailable_message(chain_id),
                            questions=_questions_for_missing_slots(["chain_id"]),
                            classification=IntentClassification(
                                mode=IntentMode.CLARIFY,
                                intent_type=classification.intent_type,
                                confidence=classification.confidence,
                                slots=classification.slots,
                                missing_slots=["chain_id"],
                                reason="rpc_unavailable",
                            ),
                            conversation_id=req.conversation_id,
                            pending=True,
                            pending_slots=partial_slots,
                        ),
                        req=req,
                        mode=IntentMode.CLARIFY,
                        intent_type=classification.intent_type,
                    )
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.QUERY,
                        assistant_message=assistant_message,
                        questions=_questions_for_missing_slots(missing_slots),
                        data=data,
                        classification=classification,
                        conversation_id=req.conversation_id,
                        pending=True,
                        pending_slots=partial_slots,
                    ),
                    req=req,
                    mode=IntentMode.QUERY,
                    intent_type=intent,
                )
            state_intent = (state.get("intent_type") or "").upper()
            if _should_interrupt_pending(
                state_intent=state_intent,
                classification=classification,
                fast_slots=fast_slots,
            ):
                if req.conversation_id:
                    delete_state(req.conversation_id)
                return _route_from_classification(req, db=db, classification=classification)
            if classification.slots:
                partial_slots.update(classification.slots)

        intent_type = (state.get("intent_type") or (classification.intent_type if classification else "") or "").upper()
        wallet_address, chain_id = _resolve_wallet_chain(req, classification, state=state)

        # QUERY follow-up
        if intent_type in _QUERY_INTENTS:
            missing: list[str] = []
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
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.CLARIFY,
                        assistant_message=_clarify_message(missing),
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
                    ),
                    req=req,
                    mode=IntentMode.CLARIFY,
                    intent_type=intent_type,
                )

            try:
                assistant_message, data = _query_payload(
                    intent_type,
                    wallet_address=wallet_address,
                    chain_id=chain_id,
                    slots=partial_slots,
                )
            except UnsupportedChainError:
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.CLARIFY,
                        assistant_message=_unsupported_chain_message(chain_id),
                        questions=_questions_for_missing_slots(["chain_id"]),
                        classification=classification
                        or _classification_from_state(
                            intent_type=intent_type,
                            slots=partial_slots,
                            missing_slots=["chain_id"],
                            reason="unsupported_chain",
                        ),
                        conversation_id=req.conversation_id,
                        pending=True,
                        pending_slots=partial_slots,
                    ),
                    req=req,
                    mode=IntentMode.CLARIFY,
                    intent_type=intent_type,
                )
            except Web3RPCError:
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.CLARIFY,
                        assistant_message=_rpc_unavailable_message(chain_id),
                        questions=_questions_for_missing_slots(["chain_id"]),
                        classification=classification
                        or _classification_from_state(
                            intent_type=intent_type,
                            slots=partial_slots,
                            missing_slots=["chain_id"],
                            reason="rpc_unavailable",
                        ),
                        conversation_id=req.conversation_id,
                        pending=True,
                        pending_slots=partial_slots,
                    ),
                    req=req,
                    mode=IntentMode.CLARIFY,
                    intent_type=intent_type,
                )
            if req.conversation_id:
                delete_state(req.conversation_id)
            return _finalize_response(
                ChatRouteResponse(
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
                ),
                req=req,
                mode=IntentMode.QUERY,
                intent_type=intent_type,
            )

        # ACTION follow-up
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
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.CLARIFY,
                        assistant_message=_clarify_message(missing),
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
                    ),
                    req=req,
                    mode=IntentMode.CLARIFY,
                intent_type=intent_type,
            )

            intent_message = (
                _build_intent_from_slots(intent_type, partial_slots)
                or state.get("intent_message")
                or req.message
            )
            settings = get_settings()
            supported_tokens = _supported_action_tokens(chain_id)
            tokens = _extract_action_tokens(partial_slots)
            unsupported = tokens - supported_tokens if supported_tokens else set()
            if unsupported:
                missing_tokens = _unsupported_token_missing_slots(intent_type)
                if req.conversation_id:
                    set_state(
                        req.conversation_id,
                        {
                            "intent_type": intent_type,
                            "intent_message": state.get("intent_message") or req.message,
                            "partial_slots": partial_slots,
                            "missing_slots": missing_tokens,
                            "wallet_address": wallet_address,
                            "chain_id": chain_id,
                        },
                    )
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.CLARIFY,
                        assistant_message=_unsupported_token_message(supported_tokens),
                        questions=_questions_for_missing_slots(missing_tokens),
                        classification=classification
                        or _classification_from_state(
                            intent_type=intent_type,
                            slots=partial_slots,
                            missing_slots=missing_tokens,
                            reason="unsupported_token",
                        ),
                        conversation_id=req.conversation_id,
                        pending=True,
                        pending_slots=partial_slots,
                    ),
                    req=req,
                    mode=IntentMode.CLARIFY,
                    intent_type=intent_type,
                )

            if _should_block_action_message(
                intent_message,
                confidence=classification.confidence if classification else None,
                supported_tokens=supported_tokens,
                settings=settings,
            ):
                logger.info("router_guard: blocked action intent", extra={"reason": "low_signal"})
                assistant_message, data, suggestions = _general_payload()
                assistant_message = "I didn't catch that. Could you rephrase what you want to do?"
                downgraded = (classification or _classification_from_state(
                    intent_type=intent_type,
                    slots=partial_slots,
                    missing_slots=[],
                    reason="low_signal_or_gibberish",
                )).model_copy(update={"mode": IntentMode.GENERAL, "reason": "low_signal_or_gibberish"})
                return _finalize_response(
                    ChatRouteResponse(
                        mode=IntentMode.GENERAL,
                        assistant_message=assistant_message,
                        questions=[],
                        data=data,
                        suggestions=suggestions,
                        classification=downgraded,
                        conversation_id=req.conversation_id,
                        pending=False,
                    ),
                    req=req,
                    mode=IntentMode.GENERAL,
                    intent_type=intent_type,
                )

            run_id = create_run_from_action(
                db=db,
                intent=intent_message,
                wallet_address=wallet_address,
                chain_id=int(chain_id),
            )
            run_result: dict[str, Any] = {}
            run_status = "CREATED"
            if not defer_start:
                run_result = start_run_for_action(db=db, run_id=run_id)
                run_status = run_result.get("status")
            fetch_url = f"/v1/runs/{run_id}?includeArtifacts=true"

            if req.conversation_id:
                delete_state(req.conversation_id)

            return _finalize_response(
                ChatRouteResponse(
                    mode=IntentMode.ACTION,
                    assistant_message=_action_message_for_status(
                        run_status,
                        artifacts=run_result.get("artifacts"),
                    ),
                    questions=[],
                    run_id=str(run_id),
                    run_ref={"id": str(run_id), "status": run_status, "fetch_url": fetch_url},
                    next_ui="SHOW_APPROVAL_SCREEN" if run_status == "AWAITING_APPROVAL" else None,
                    classification=classification,
                    conversation_id=req.conversation_id,
                ),
                req=req,
                mode=IntentMode.ACTION,
                intent_type=intent_type,
                status=run_status,
            )

        # default follow-up fallback
        return _finalize_response(
            ChatRouteResponse(
                mode=IntentMode.CLARIFY,
                assistant_message=_clarify_message(missing_slots),
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
            ),
            req=req,
            mode=IntentMode.CLARIFY,
            intent_type=intent_type,
        )

    # First message path (no pending state)
    raw = classify_intent(req.message, context)
    try:
        classification = IntentClassification.model_validate(raw)
    except Exception:
        classification = IntentClassification(
            mode=IntentMode.CLARIFY,
            missing_slots=["clarification"],
            reason="invalid_classification",
        )
    classification = _normalize_classification(classification)
    return _route_from_classification(req, db=db, classification=classification)
