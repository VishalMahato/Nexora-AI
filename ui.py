from __future__ import annotations

import json
import time
import uuid
import threading
from typing import Any

import requests
import streamlit as st


DEFAULT_BASE_URL = "http://localhost:8000"
CHAIN_OPTIONS = {
    "Ethereum Mainnet": 1,
    "Sepolia": 11155111,
}
STEP_DESCRIPTIONS = {
    "INPUT_NORMALIZE": "🧠 Understanding Request",
    "WALLET_SNAPSHOT": "👛 Analyzing Wallet",
    "PLAN_TX": "📝 Creating Transaction Plan",
    "BUILD_TXS": "🏗️ Building Transactions",
    "SIMULATE_TXS": "🔮 Simulating Outcome",
    "POLICY_EVAL": "🛡️ Checking Policies",
    "SECURITY_EVAL": "🔒 Security Scan",
    "JUDGE_AGENT": "⚖️ Evaluating",
    "REPAIR_ROUTER": "🔧 Attempting Repair",
    "REPAIR_PLAN_TX": "🛠️ Adjusting Plan",
    "FINALIZE": "✅ Finalizing",
}




def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _log_call(message: str) -> None:
    """Log to both console and session state for debugging."""
    try:
        ts = time.strftime("%H:%M:%S")
        entry = f"{ts} | {message}"
        
        # Always print to console
        print(entry)
        
        # Also store in session state if available
        if "call_log" in st.session_state:
            st.session_state["call_log"].append(entry)
            if len(st.session_state["call_log"]) > 100:
                st.session_state["call_log"] = st.session_state["call_log"][-100:]
    except Exception as e:
        print(f"LOG ERROR: {e}")


def _api_request(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[bool, Any]:
    try:
        _log_call(f"{method} {url}")
        if method == "GET":
            resp = requests.get(url, timeout=12)
        else:
            resp = requests.post(url, json=payload, timeout=620)
        if resp.status_code >= 400:
            _log_call(f"ERR {resp.status_code} {url}")
            return False, {"error": f"{resp.status_code} {resp.text}"}
        if resp.text.strip() == "":
            _log_call(f"ERR empty body {url}")
            return False, {"error": "empty response body"}
        _log_call(f"OK {resp.status_code} {url}")
        return True, resp.json()
    except requests.RequestException as exc:
        _log_call(f"EXC {url} {exc}")
        return False, {"error": str(exc)}


def _stream_chat(payload: dict[str, Any], on_delta=None) -> tuple[bool, Any]:
    try:
        _log_call("POST /v1/chat/route/stream")
        resp = requests.post(
            f"{st.session_state['base_url']}/v1/chat/route/stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=600,
        )
        if resp.status_code >= 400:
            _log_call(f"ERR {resp.status_code} /v1/chat/route/stream")
            return False, {"error": f"{resp.status_code} {resp.text}"}
        final = None
        full_text = ""
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload_text = line[len("data:") :].strip()
            if not payload_text:
                continue
            try:
                event = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "delta":
                chunk = event.get("content") or ""
                full_text += chunk
                if on_delta:
                    on_delta(full_text)
            if event.get("type") == "final":
                final = event.get("response")
                break
        if not final:
            _log_call("ERR stream ended without final response")
            return False, {"error": "stream ended without final response"}
        _log_call("OK /v1/chat/route/stream")
        return True, final
    except requests.RequestException as exc:
        _log_call(f"EXC /v1/chat/route/stream {exc}")
        return False, {"error": str(exc)}


def _get_run_payload(run_data: dict[str, Any]) -> dict[str, Any]:
    if "run" in run_data:
        return run_data.get("run") or {}
    return run_data


def _init_state() -> None:
    st.session_state.setdefault("conversation_id", str(uuid.uuid4()))
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("run_id", None)
    st.session_state.setdefault("run_data", None)
    st.session_state.setdefault("last_router", None)
    st.session_state.setdefault("chat_input", "")
    st.session_state.setdefault("base_url", DEFAULT_BASE_URL)
    st.session_state.setdefault("last_execute", None)
    st.session_state.setdefault("chain_label", list(CHAIN_OPTIONS.keys())[0])
    st.session_state.setdefault("show_last_json", False)
    st.session_state.setdefault("is_sending", False)
    st.session_state.setdefault("pending_message", None)
    st.session_state.setdefault("pending_wallet", None)
    st.session_state.setdefault("pending_chain_id", None)
    st.session_state.setdefault("clear_input", False)
    st.session_state.setdefault("run_events", [])
    st.session_state.setdefault("run_event_seen", set())
    st.session_state.setdefault("run_events_run_id", None)
    st.session_state.setdefault("run_status_live", None)
    st.session_state.setdefault("event_poll_enabled", True)
    st.session_state.setdefault("call_log", [])


def _append_message(role: str, content: str) -> None:
    ts = time.strftime("%H:%M")
    st.session_state["messages"].append({"role": role, "content": content, "ts": ts})


def _is_valid_wallet_address(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    if not value.startswith("0x"):
        return False
    return len(value) == 42


def _build_history_payload() -> list[dict[str, str]]:
    history = st.session_state.get("messages", [])[-8:]
    return [
        {"role": item.get("role", ""), "content": item.get("content", "")}
        for item in history
        if item.get("content")
    ]


def _build_chat_payload(message: str, wallet: str | None, chain_id: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": message,
        "conversation_id": st.session_state["conversation_id"],
        "metadata": {"history": _build_history_payload(), "defer_start": True},
    }
    if wallet:
        payload["wallet_address"] = wallet
    if chain_id:
        payload["chain_id"] = chain_id
    return payload


def _start_run_background(run_id: str) -> None:
    base_url = st.session_state.get("base_url", DEFAULT_BASE_URL)

    def _runner() -> None:
        try:
            _log_call(f"POST /v1/runs/{run_id}/start (background)")
            requests.post(
                f"{base_url}/v1/runs/{run_id}/start",
                timeout=600,
            )
            _log_call(f"OK /v1/runs/{run_id}/start (background)")
        except requests.RequestException as exc:
            _log_call(f"EXC /v1/runs/{run_id}/start {exc}")
            return

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()


def _reset_run_events(run_id: str | None) -> None:
    _log_call(f"RESET_EVENTS for run_id={run_id}")
    st.session_state["run_events"] = []
    st.session_state["run_event_seen"] = set()
    st.session_state["run_events_run_id"] = run_id
    st.session_state["run_status_live"] = None


def _consume_run_events(run_id: str) -> bool:
    """
    Consumes SSE events from the run events endpoint.
    Returns True if new events were added.
    """
    if not run_id:
        _log_call("CONSUME_EVENTS: No run_id provided")
        return False
    
    if st.session_state.get("run_events_run_id") != run_id:
        _reset_run_events(run_id)
    
    added = False
    resp = None
    
    try:
        _log_call(f"GET /v1/runs/{run_id[:8]}../events (SSE)")
        
        # Use longer timeout for SSE - server may keep connection open
        resp = requests.get(
            f"{st.session_state['base_url']}/v1/runs/{run_id}/events",
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=(5, 300),  # 5s to connect, 300s to read (support long runs)
        )
        
        if resp.status_code >= 400:
            _log_call(f"ERR {resp.status_code} /v1/runs/{run_id[:8]}../events")
            return False
        
        _log_call(f"OK {resp.status_code} /v1/runs/{run_id[:8]}../events - streaming")
        
        # Read events with a time limit to avoid blocking UI too long
        start = time.time()
        max_read_time = 3.0  # Maximum 3 seconds to read events per poll
        event_count = 0
        
        for raw_line in resp.iter_lines(decode_unicode=True, chunk_size=1):
            # Check if we've spent too long reading
            if time.time() - start > max_read_time:
                _log_call(f"MAX READ TIME reached after {event_count} events")
                break
            
            if not raw_line:
                continue
            
            line = raw_line.strip()
            
            # Handle SSE event format
            if not line.startswith("data:"):
                continue
            
            payload_text = line[len("data:"):].strip()
            if not payload_text:
                continue
            
            try:
                event = json.loads(payload_text)
                event_count += 1
            except json.JSONDecodeError as e:
                _log_call(f"JSON decode error: {e} for line: {payload_text[:100]}")
                continue
            
            # Create unique key for deduplication
            event_type = event.get("type", "")
            key = (
                event.get("eventId")
                or f"{event_type}|{event.get('step')}|{event.get('status')}|{event.get('summary')}|{event.get('timestamp')}"
            )
            
            seen = st.session_state.get("run_event_seen", set())
            if key in seen:
                # _log_call(f"SKIP duplicate event: {key[:80]}")
                continue
            
            seen.add(key)
            st.session_state["run_event_seen"] = seen
            
            # Process different event types
            if event_type == "run_step":
                step_data = {
                    "step": event.get("step"),
                    "status": event.get("status"),
                    "summary": event.get("summary"),
                    "timestamp": event.get("timestamp"),
                }
                st.session_state["run_events"].append(step_data)
                added = True
                _log_call(f"EVENT run_step: {event.get('step')} - {event.get('status')}")
                
            elif event_type == "run_status":
                new_status = event.get("status")
                st.session_state["run_status_live"] = new_status
                added = True
                _log_call(f"EVENT run_status: {new_status}")
            
            else:
                _log_call(f"EVENT unknown type: {event_type}")
        
        if added:
            _log_call(f"CONSUMED {event_count} new events, total: {len(st.session_state.get('run_events', []))}")
        else:
            _log_call(f"NO NEW EVENTS ({event_count} processed)")
    
    except requests.Timeout as exc:
        _log_call(f"TIMEOUT /v1/runs/{run_id[:8]}../events: {exc}")
        return False
    except requests.exceptions.ChunkedEncodingError as exc:
        # This can happen when the connection closes - may be normal
        _log_call(f"CHUNKED ENCODING ERROR (connection closed): {exc}")
    except requests.RequestException as exc:
        _log_call(f"EXC /v1/runs/{run_id[:8]}../events: {exc}")
    except Exception as exc:
        _log_call(f"UNEXPECTED EXC in event loop: {exc}")
    finally:
        # Always close the connection
        if resp:
            try:
                resp.close()
                _log_call(f"CLOSED SSE connection for run {run_id[:8]}..")
            except Exception:
                pass
    
    return added


def _render_chat(messages: list[dict[str, Any]], streaming_text: str | None = None) -> str:
    chat_parts = ["<div class='chat-container'>"]
    for msg in messages:
        role = msg.get("role", "assistant")
        content = _escape(msg.get("content", "")).replace("\n", "<br/>")
        ts = _escape(msg.get("ts", ""))
        chat_parts.append(
            f"<div class='message {role}'><div class='message-bubble'>"
            f"{content}<div class='message-time'>{ts}</div></div></div>"
        )
    if streaming_text is not None:
        content = _escape(streaming_text).replace("\n", "<br/>")
        ts = _escape(time.strftime("%H:%M"))
        chat_parts.append(
            f"<div class='message assistant'><div class='message-bubble'>"
            f"{content}<div class='loading-dots'><span class='loading-dot'></span>"
            f"<span class='loading-dot'></span><span class='loading-dot'></span></div>"
            f"<div class='message-time'>{ts}</div></div></div>"
        )
    
    chat_parts.append("</div>")
    return "".join(chat_parts)


def _render_status_bubble(step: str, status: str) -> str:
    return f"""
    <div class="status-bubble-container">
        <div class="status-bubble">
            <div class="status-spinner"></div>
            <div>
                <div style="font-size: 0.75rem; opacity: 0.8; margin-bottom: 0.2rem;">{status}</div>
                <div style="font-weight: 600;">{step}</div>
            </div>
        </div>
    </div>
    """


def _queue_chat(message: str, wallet: str | None, chain_id: int | None) -> None:
    if not message.strip():
        return
    if not _is_valid_wallet_address(wallet):
        wallet = None
    _append_message("user", message)
    st.session_state["pending_message"] = message
    st.session_state["pending_wallet"] = wallet
    st.session_state["pending_chain_id"] = chain_id
    st.session_state["is_sending"] = True
    st.session_state["clear_input"] = True


def _refresh_run() -> None:
    run_id = st.session_state.get("run_id")
    if not run_id:
        return
    ok, data = _api_request(
        "GET",
        f"{st.session_state['base_url']}/v1/runs/{run_id}?includeArtifacts=true",
    )
    if ok:
        st.session_state["run_data"] = data


def _approve_run() -> None:
    run_id = st.session_state.get("run_id")
    if not run_id:
        return
    ok, data = _api_request(
        "POST",
        f"{st.session_state['base_url']}/v1/runs/{run_id}/approve",
        payload={"reviewer": "streamlit"},
    )
    if ok:
        st.success(f"✅ Approved: {data.get('status')}")
        _refresh_run()
    else:
        st.error(f"❌ {data.get('error')}")


def _execute_run() -> None:
    run_id = st.session_state.get("run_id")
    if not run_id:
        return
    ok, data = _api_request(
        "POST",
        f"{st.session_state['base_url']}/v1/runs/{run_id}/execute",
    )
    if ok:
        st.session_state["last_execute"] = data
        st.success("✅ Execution prepared successfully!")
    else:
        st.error(f"❌ {data.get('error')}")


def _on_send() -> None:
    # Check widget input (chat_input_val)
    message = st.session_state.get("chat_input_val") or st.session_state.get("chat_input", "")
    wallet_value = st.session_state.get("wallet_address") or None
    wallet = wallet_value if _is_valid_wallet_address(wallet_value) else None
    chain_label = st.session_state.get("chain_label")
    chain_id = CHAIN_OPTIONS.get(chain_label)
    _queue_chat(message, wallet, chain_id)


def _on_clear_chat() -> None:
    st.session_state["messages"] = []
    st.session_state["last_router"] = None
    st.session_state["chat_input"] = ""
    st.session_state["pending_message"] = None
    st.session_state["pending_wallet"] = None
    st.session_state["pending_chain_id"] = None
    st.session_state["is_sending"] = False
    _reset_run_events(st.session_state.get("run_id"))


# Initialize
st.set_page_config(
    page_title="Nexora",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

_init_state()
if st.session_state.get("clear_input"):
    st.session_state["chat_input"] = ""
    st.session_state["chat_input_val"] = ""
    st.session_state["clear_input"] = False

# === HIGHLY CUSTOMIZED CSS ===
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

/* === GLOBAL === */
* {
    font-family: 'Inter', sans-serif;
    box-sizing: border-box;
}

body {
    background-color: #030712;
    color: #e0e7ff;
}

.stApp {
    background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #030712 60%);
    background-attachment: fixed;
}

/* Hide Streamlit cruft */
#MainMenu, footer, header { visibility: hidden; }

/* === HEADER CARD === */
.nexora-header {
    background: rgba(17, 24, 39, 0.6);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: 24px;
    padding: 2.5rem 3rem;
    margin-bottom: 3rem;
    box-shadow: 0 0 40px rgba(79, 70, 229, 0.15);
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: relative;
    overflow: hidden;
}

.nexora-header::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 24px;
    padding: 1px;
    background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.5), transparent);
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    pointer-events: none;
}

.header-title h1 {
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    letter-spacing: -0.08rem;
    text-shadow: 0 0 30px rgba(99, 102, 241, 0.3);
}

.header-title p {
    color: #818cf8;
    margin: 0.5rem 0 0 0;
    font-size: 1.1rem;
    font-weight: 500;
    letter-spacing: 0.02em;
}

.status-badge {
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #34d399;
    padding: 0.6rem 1.2rem;
    border-radius: 9999px;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1rem;
    box-shadow: 0 0 20px rgba(16, 185, 129, 0.1);
}

.status-badge .dot {
    width: 6px;
    height: 6px;
    background: #34d399;
    border-radius: 50%;
    box-shadow: 0 0 10px #34d399;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { opacity: 0.5; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.2); }
    100% { opacity: 0.5; transform: scale(0.8); }
}

/* === CHAT AREA === */
.chat-container {
    background: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 24px;
    padding: 2.5rem;
    min-height: 500px;
    max-height: 650px;
    overflow-y: auto;
    position: relative;
    backdrop-filter: blur(12px);
    /* Subtle Grid Pattern */
    background-image: linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
    background-size: 40px 40px;
}

.chat-container::-webkit-scrollbar { width: 8px; }
.chat-container::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
.chat-container::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
.chat-container::-webkit-scrollbar-thumb:hover { background: #6b7280; }

/* Messages */
.message {
    margin-bottom: 2rem;
    display: flex;
    animation: slideUp 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes slideUp {
    from { opacity: 0; transform: translateY(15px); }
    to { opacity: 1; transform: translateY(0); }
}

.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }

.message-bubble {
    max-width: 75%;
    padding: 1.25rem 1.75rem;
    border-radius: 22px;
    position: relative;
    line-height: 1.6;
    font-size: 1.05rem;
}

.message.user .message-bubble {
    background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%);
    color: #fff;
    border-bottom-right-radius: 4px;
    box-shadow: 0 8px 20px -5px rgba(79, 70, 229, 0.4);
    border: 1px solid rgba(165, 180, 252, 0.1);
}

.message.assistant .message-bubble {
    background: rgba(30, 41, 59, 0.8);
    color: #e0e7ff;
    border-bottom-left-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.message-time {
    margin-top: 0.5rem;
    font-size: 0.75rem;
    opacity: 0.5;
    text-align: right;
    font-weight: 500;
}

/* === STATUS BUBBLE === */
.status-bubble-container {
    display: flex;
    justify-content: flex-start;
    margin-top: 1.5rem;
    animation: fadeIn 0.4s ease-out;
}

.status-bubble {
    background: rgba(49, 46, 129, 0.4);
    border: 1px solid #6366f1;
    border-radius: 18px;
    padding: 1rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    backdrop-filter: blur(12px);
    box-shadow: 0 0 30px rgba(99, 102, 241, 0.1);
    min-width: 320px;
}

.status-spinner {
    width: 24px;
    height: 24px;
    border: 3px solid rgba(165, 180, 252, 0.1);
    border-top-color: #818cf8;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

.status-text {
    display: flex;
    flex-direction: column;
}

.status-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    color: #818cf8;
    font-weight: 700;
    letter-spacing: 0.08em;
    margin-bottom: 0.25rem;
}

.status-step {
    font-weight: 600;
    color: #fff;
    font-size: 0.95rem;
}

/* === BUTTONS & INPUTS === */
.stTextArea textarea {
    background-color: rgba(17, 24, 39, 0.6) !important;
    border: 1px solid rgba(75, 85, 99, 0.5) !important;
    border-radius: 16px !important;
    color: white !important;
    font-family: 'JetBrains Mono', monospace !important;
    padding: 1rem !important;
    transition: all 0.2s !important;
}

.stTextArea textarea:focus {
    border-color: #818cf8 !important;
    box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.2) !important;
    background-color: rgba(17, 24, 39, 0.9) !important;
}

.stButton button {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
    border: none;
    padding: 0.85rem 0;
    font-weight: 700;
    border-radius: 14px;
    color: white;
    transition: all 0.2s;
    letter-spacing: 0.02em;
    font-size: 0.95rem;
    box-shadow: 0 4px 15px -3px rgba(99, 102, 241, 0.4);
}

.stButton button:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.6);
    filter: brightness(1.1);
}

.stButton button:active:not(:disabled) {
    transform: translateY(0);
}

/* Context Buttons */
.action-btn-approve button {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    box-shadow: 0 0 20px rgba(16, 185, 129, 0.3) !important;
}
.action-btn-approve button:hover {
    box-shadow: 0 0 30px rgba(16, 185, 129, 0.5) !important;
}

.action-btn-execute button {
    background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%) !important;
    box-shadow: 0 0 20px rgba(139, 92, 246, 0.3) !important;
}
.action-btn-execute button:hover {
    box-shadow: 0 0 30px rgba(139, 92, 246, 0.5) !important;
}

/* === TABS === */
.stTabs [data-baseweb="tab-list"] {
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #94a3b8;
    border: none;
    font-weight: 600;
    padding: 0.75rem 0;
    font-size: 1rem;
    transition: all 0.2s;
}

.stTabs [data-baseweb="tab"]:hover {
    color: #e0e7ff;
}

.stTabs [aria-selected="true"] {
    color: #818cf8;
    border-bottom: 2px solid #818cf8;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #020617;
    border-right: 1px solid #1e1b4b;
}
</style>
""", unsafe_allow_html=True)


# Sidebar (Cleaned up)
with st.sidebar:
    st.markdown('<div class="sidebar-section">CONFIGURATION</div>', unsafe_allow_html=True)
    st.text_input("Backend URL", key="base_url")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("PING", use_container_width=True):
            ok, data = _api_request("GET", f"{st.session_state['base_url']}/healthz")
            if ok:
                st.toast("✅ Backend Connected")
            else:
                st.toast(f"❌ {data.get('error')}")
    
    with col2:
        if st.button("RESET", use_container_width=True):
            st.session_state["conversation_id"] = str(uuid.uuid4())
            st.session_state["messages"] = []
            st.session_state["run_id"] = None
            st.session_state["run_data"] = None
            st.session_state["last_router"] = None
            st.session_state["pending_message"] = None
            st.session_state["is_sending"] = False
            _reset_run_events(None)
            st.rerun()
    
    st.markdown("---")
    st.text_input("Wallet", key="wallet_address", placeholder="0x...")
    st.selectbox("Network", list(CHAIN_OPTIONS.keys()), key="chain_label")
    
    st.markdown("---")
    st.checkbox("Debug Mode", key="show_last_json")

# Header
st.markdown("""
<div class="nexora-header">
    <div class="header-title">
        <h1>Nexora</h1>
        <p>Advanced Web3 Intent Copilot</p>
    </div>
    <div class="status-badge">
        <div class="dot"></div> ONLINE
    </div>
</div>
""", unsafe_allow_html=True)

# Main Logic
tab_chat, tab_debug = st.tabs(["INTERFACE", "DEBUG"])

with tab_chat:
    messages = st.session_state["messages"]
    run_id = st.session_state.get("run_id")
    
    # Check if run is active (Logic for Locking UI)
    terminal_statuses = {
        "AWAITING_APPROVAL",
        "APPROVED_READY", 
        "SUBMITTED",
        "CONFIRMED",
        "REVERTED",
        "BLOCKED",
        "FAILED",
        "REJECTED",
        "COMPLETED",
    }
    
    is_run_active = False
    
    chat_area = st.empty()
    status_area = st.empty()
    action_area = st.empty() # New Area for Buttons
    
    chat_area.markdown(_render_chat(messages), unsafe_allow_html=True)

    # --- INPUT AREA (Placed before loop to ensure rendering) ---
    st.markdown("### ⚡ Command")
    
    input_disabled = st.session_state["is_sending"] or is_run_active
    input_placeholder = "Processing..." if is_run_active else "Describe your intent (e.g., 'Swap 100 USDC to ETH')..."

   
    # Note: Streamlit text_area submitting via Enter requires Ctrl+Enter. 
    # True "Enter to send" in text_input requires preventing multiline. 
    
    def _handle_text_area_change():
        # This triggers on Ctrl+Enter
        if st.session_state["chat_input_val"]:
             _on_send()

    st.text_area(
        "Message",
        key="chat_input_val", # Changed key to avoid conflict or loop issues if I used chat_input widget before
        placeholder=input_placeholder,
        height=80,
        label_visibility="collapsed",
        disabled=input_disabled,
        value=st.session_state.get("chat_input", "") # Bind to state
    )

    col1, col2 = st.columns([4, 1])
    with col1:
        if is_run_active:
             st.button("Running...", disabled=True, use_container_width=True)
        elif st.session_state["is_sending"]:
             st.button("Sending...", disabled=True, use_container_width=True)
        else:
             st.button("SEND COMMAND", on_click=_on_send, use_container_width=True, type="primary")
             st.caption("Tip: Press Ctrl+Enter to send")
             
    with col2:
        st.button("🗑️ CLEAR", on_click=_on_clear_chat, use_container_width=True)

    st.markdown("---") # Divider
    # ---------------------------------------------------------

    # Polling Loop covering the status bubble (Robust Stateless Polling)
    # We poll the RUN OBJECT instead of streaming events to prevent DB pool exhaustion.
    if run_id and not st.session_state.get("is_sending"):
        _log_call(f"POLL START: {run_id}")
        
        while True:
            try:
                # 1. Fetch Run Data (Stateless Request)
                _refresh_run()
                run_data_full = st.session_state.get("run_data") or {}
                run_payload = _get_run_payload(run_data_full)
                
                # DEBUG: Log structure
                # _log_call(f"Status: {run_payload.get('status')} | Keys: {list(run_payload.keys())}")
                # artifacts = run_data_full.get("artifacts") or run_payload.get("artifacts") or {}
                # _log_call(f"Artifacts Keys: {list(artifacts.keys())} | Timeline len: {len(artifacts.get('timeline', []))}")
                
                # DEBUG: Dump to file for agent inspection
                import json
                try:
                    with open("last_run_debug.json", "w") as f:
                        json.dump(run_data_full, f, indent=2, default=str)
                except Exception:
                    pass

                # 2. Extract Status & Steps
                current_status = run_payload.get("status")
                if not current_status and st.session_state.get("run_status_live"):
                     current_status = st.session_state.get("run_status_live")

                # Get steps from artifacts.timeline if available
                # Note: artifacts might be in root or inside run payload
                artifacts = run_data_full.get("artifacts") or run_payload.get("artifacts") or {}
                timeline = artifacts.get("timeline") or []
                
                # Render Bubble
                is_active = (current_status not in terminal_statuses) if current_status else True
                
                if timeline or is_active:
                     # Get latest step
                     if timeline:
                         last_entry = timeline[-1]
                         raw_step = last_entry.get("step") or  last_entry.get("name")
                         step_name = STEP_DESCRIPTIONS.get(raw_step, raw_step.replace("_", " ").title() if raw_step else "Processing...")
                         step_status = last_entry.get("status") or "ACTIVE"
                     else:
                         step_name = "Initializing..."
                         step_status = "STARTING"
                     
                     # Overrides
                     bubble_title = step_status
                     bubble_subtitle = step_name
                     spinner_color = "#34d399"

                     if current_status == "AWAITING_APPROVAL":
                        bubble_title = "ACTION REQUIRED"
                        bubble_subtitle = "📝 Waiting for Approval"
                        spinner_color = "#fbbf24"
                     elif current_status == "APPROVED_READY":
                        bubble_title = "READY"
                        bubble_subtitle = "🚀 Ready to Execute"
                        spinner_color = "#8b5cf6"
                     
                     if is_active or current_status == "COMPLETED" or current_status == "AWAITING_APPROVAL" or current_status == "APPROVED_READY":
                         status_html = f"""
                            <div class="status-bubble-container">
                                <div class="status-bubble">
                                    <div class="status-spinner" style="border-color: {spinner_color}; border-top-color: transparent;"></div>
                                    <div class="status-text">
                                        <span class="status-label">{bubble_title}</span>
                                        <span class="status-step">{bubble_subtitle}</span>
                                    </div>
                                </div>
                            </div>
                        """
                         status_area.markdown(status_html, unsafe_allow_html=True)
                     else:
                         status_area.empty()
                
                # 3. Handle Terminal States
                if current_status in terminal_statuses:
                    _log_call(f"Run Finished: {current_status}")
                    st.rerun()

                # 4. Render Action Buttons
                if current_status == "AWAITING_APPROVAL":
                     action_area.empty()
                     with action_area.container():
                         st.markdown('<div class="action-btn-approve">', unsafe_allow_html=True)
                         if st.button("✅ APPROVE TRANSACTION", use_container_width=True, key=f"btn_approve_poll"):
                             _approve_run()
                             st.rerun()
                         st.markdown('</div>', unsafe_allow_html=True)
                elif current_status == "APPROVED_READY":
                     action_area.empty()
                     with action_area.container():
                         st.markdown('<div class="action-btn-execute">', unsafe_allow_html=True)
                         if st.button("🚀 EXECUTE TRANSACTION", use_container_width=True, key=f"btn_execute_poll"):
                             _execute_run()
                             st.rerun()
                         st.markdown('</div>', unsafe_allow_html=True)
                else:
                     action_area.empty()

                if current_status and current_status not in terminal_statuses:
                    pass # Continue loop

                time.sleep(1) # Poll every 1s (Friendly to DB)

            except Exception as e:
                _log_call(f"Poll Error: {e}")
                time.sleep(2)

    # Fallback check
    if run_id:
        run_payload = _get_run_payload(st.session_state.get("run_data") or {})
        current_status =  st.session_state.get("run_status_live") or run_payload.get("status")
        # Ensure buttons show up even if we aren't in the actively polling loop (e.g. page refresh)
        if current_status == "AWAITING_APPROVAL":
             st.markdown('<div class="action-btn-approve">', unsafe_allow_html=True)
             if st.button("✅ APPROVE TRANSACTION", use_container_width=True, key="btn_approve_static"):
                 _approve_run()
                 st.rerun()
             st.markdown('</div>', unsafe_allow_html=True)
        elif current_status == "APPROVED_READY":
             st.markdown('<div class="action-btn-execute">', unsafe_allow_html=True)
             if st.button("🚀 EXECUTE TRANSACTION", use_container_width=True, key="btn_execute_static"):
                 _execute_run()
                 st.rerun()
             st.markdown('</div>', unsafe_allow_html=True)

        if current_status and current_status not in terminal_statuses:
            is_run_active = True

    # Streaming Logic
    if st.session_state.get("pending_message"):
        payload = _build_chat_payload(
            st.session_state["pending_message"],
            st.session_state.get("pending_wallet"),
            st.session_state.get("pending_chain_id"),
        )
        
        def on_delta(text: str) -> None:
            chat_area.markdown(_render_chat(messages, streaming_text=text), unsafe_allow_html=True)
            
        ok, data = _stream_chat(payload, on_delta=on_delta)
        if ok:
            st.session_state["last_router"] = data
            assistant_message = data.get("assistant_message") or "Received."
            _append_message("assistant", assistant_message)
            
            # Check for new run
            run_ref = data.get("run_ref") or {}
            new_run_id = data.get("run_id") or run_ref.get("id")
            if new_run_id:
                if st.session_state.get("run_id") != new_run_id:
                    _reset_run_events(new_run_id)
                st.session_state["run_id"] = new_run_id
                _refresh_run()
                if run_ref.get("status") == "CREATED":
                    _start_run_background(str(new_run_id))
        else:
             _append_message("assistant", f"Error: {data.get('error')}")
             
        st.session_state["pending_message"] = None
        st.session_state["is_sending"] = False
        st.session_state["clear_input"] = True
        st.rerun()





# Validates if data can be displayed via st.json
def _safe_json(data: Any, label: str) -> None:
    st.markdown(f"### {label}")
    if data is None:
        st.caption("None")
        return
    if isinstance(data, (dict, list)):
        st.json(data)
    else:
        # Try to parse string as JSON, else show as text
        if isinstance(data, str):
            try:
                st.json(json.loads(data))
                return
            except json.JSONDecodeError:
                pass
        st.write(data)

with tab_debug:
    _safe_json(st.session_state.get("last_router"), "📡 API Response (Last Router)")
    _safe_json(st.session_state.get("run_data"), "🏃 Run Data")
    _safe_json(st.session_state.get("last_execute"), "🚀 Execution Result") # Added Step 3.2 display
    
    st.markdown("### 📜 Logs")
    st.text_area("Log Output", "\n".join(st.session_state.get("call_log", [])), height=300)
