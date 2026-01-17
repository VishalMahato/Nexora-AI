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
            timeout=(5, 30),  # 5s to connect, 30s to read
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
                _log_call(f"SKIP duplicate event: {key[:80]}")
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
    message = st.session_state.get("chat_input", "")
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
    page_title="Nexora - Web3 Intent Copilot",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

_init_state()
if st.session_state.get("clear_input"):
    st.session_state["chat_input"] = ""
    st.session_state["clear_input"] = False

# Minimal inline styles for MVP
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Hide Streamlit branding */
#MainMenu, footer, header {
    visibility: hidden;
}

.block-container {
    padding: 1rem 2rem 2rem 2rem;
    max-width: 1200px;
}

/* Chat Container - Prevent reflow */
.chat-container { 
    background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%);
    border: 1px solid #e2e8f0;
    border-radius: 16px; 
    padding: 1.5rem; 
    margin: 1rem 0; 
    min-height: 500px;
    max-height: 600px;
    overflow-y: auto;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    /* Prevent layout shift */
    contain: layout;
}

.chat-container::-webkit-scrollbar {
    width: 8px;
}

.chat-container::-webkit-scrollbar-track {
    background: transparent;
}

.chat-container::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
}

.chat-container::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
}

/* Messages */
.message { 
    margin: 0 0 1rem 0;
    display: flex;
    /* Smooth appearance */
    opacity: 1;
    transform: translateY(0);
}

.message.user { 
    justify-content: flex-end; 
}

.message.assistant { 
    justify-content: flex-start; 
}

.message-bubble { 
    padding: 0.875rem 1.125rem;
    border-radius: 16px;
    max-width: 75%;
    line-height: 1.5;
    word-wrap: break-word;
}

.message.user .message-bubble { 
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
    color: white;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

.message.assistant .message-bubble { 
    background: white;
    color: #1e293b;
    border: 1px solid #e2e8f0;
    border-bottom-left-radius: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.message-time { 
    font-size: 0.75rem;
    opacity: 0.6;
    margin-top: 0.375rem;
    font-weight: 500;
}

/* Status message bubble */
.message.status .message-bubble {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    color: #0369a1;
    border-radius: 12px;
}

/* Loading dots */
.loading-dots { 
    display: inline-flex;
    gap: 0.25rem;
    margin-left: 0.5rem;
}

.loading-dot { 
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.6;
    animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dot:nth-child(1) { animation-delay: -0.32s; }
.loading-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
    0%, 80%, 100% { 
        transform: scale(0.8);
        opacity: 0.5;
    }
    40% { 
        transform: scale(1);
        opacity: 1;
    }
}

/* Step indicator */
.step-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.875rem;
    background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
    border: 1px solid #93c5fd;
    border-radius: 20px;
    font-size: 0.875rem;
    font-weight: 600;
    color: #1e40af;
    margin-top: 0.5rem;
}

.step-indicator .step-name {
    font-weight: 700;
}

.step-indicator .step-status {
    font-weight: 500;
    opacity: 0.9;
}

.step-indicator.running {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-color: #fbbf24;
    color: #92400e;
}

.step-indicator.done {
    background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
    border-color: #34d399;
    color: #065f46;
}

/* Header */
.nexora-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 20px;
    padding: 2rem;
    margin-bottom: 1.5rem;
    color: white;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.nexora-header h1 {
    margin: 0 0 0.5rem 0;
    font-size: 2.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.nexora-header p {
    margin: 0;
    opacity: 0.95;
    font-size: 1.125rem;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 12px;
    font-weight: 600;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
    background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%);
}

.stButton > button:active {
    transform: translateY(0);
}

.stButton > button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none !important;
}

/* Input fields */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > select {
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    transition: all 0.2s ease;
    background: white;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stSelectbox > div > div > select:focus {
    border-color: #6366f1;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
    outline: none;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    background: white;
    padding: 0.5rem;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
}

.stTabs [data-baseweb="tab"] {
    padding: 0.75rem 1.25rem;
    border-radius: 8px;
    font-weight: 600;
    color: #64748b;
    transition: all 0.2s ease;
}

.stTabs [data-baseweb="tab"]:hover {
    background: #f1f5f9;
    color: #1e293b;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

/* Sidebar */
.css-1d391kg, [data-testid="stSidebar"] {
    background: white;
    border-right: 1px solid #e2e8f0;
}

/* Info boxes */
.stAlert {
    border-radius: 12px;
    border-left-width: 4px;
}

/* Prevent layout shift on rerun */
[data-testid="stMarkdownContainer"] {
    contain: layout;
}
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.text_input("Backend URL", key="base_url")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Check", use_container_width=True):
            ok, data = _api_request("GET", f"{st.session_state['base_url']}/healthz")
            if ok:
                st.success("✅ Connected")
            else:
                st.error(f"❌ {data.get('error')}")
    
    with col2:
        if st.button("🔄 New Chat", use_container_width=True):
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
    st.text_input("Wallet Address", key="wallet_address", placeholder="0x...")
    st.selectbox("Network", list(CHAIN_OPTIONS.keys()), key="chain_label")
    
    if st.session_state.get("run_id"):
        st.markdown("---")
        st.markdown("### 🎯 Run Controls")
        st.text(f"Run: {st.session_state.get('run_id')[:8]}...")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔄", help="Refresh", use_container_width=True):
                _refresh_run()
                st.rerun()
        with col2:
            if st.button("✅", help="Approve", use_container_width=True):
                _approve_run()
                st.rerun()
        with col3:
            if st.button("▶️", help="Execute", use_container_width=True):
                _execute_run()
                st.rerun()
    
    st.markdown("---")
    st.checkbox("🔍 Show Debug", key="show_last_json")

# Header
st.markdown("# 🔮 Nexora")
st.markdown("Web3 Intent Copilot - Safe, Explainable Blockchain Actions")

# Main Tabs
tab_chat, tab_timeline, tab_debug = st.tabs(["💬 Chat", "📊 Timeline", "🔧 Debug"])

with tab_chat:
    messages = st.session_state["messages"]
    run_id = st.session_state.get("run_id")
    
    # CRITICAL: Poll for events if we have an active run
    _log_call(f"=== RENDER START: run_id={run_id}, is_sending={st.session_state.get('is_sending')} ===")
    
    new_event = False
    should_continue_polling = False
    
    if run_id and not st.session_state.get("is_sending"):
        _log_call(f"ATTEMPTING to consume events for run {run_id[:8]}..")
        new_event = _consume_run_events(str(run_id))
        _log_call(f"CONSUME returned: new_event={new_event}")
        
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
        
        live_status = st.session_state.get("run_status_live")   
        run_payload = _get_run_payload(st.session_state.get("run_data") or {})
        current_status = live_status or run_payload.get("status")
        
        _log_call(f"STATUS: live={live_status}, stored={run_payload.get('status')}, current={current_status}")
        
        if st.session_state.get("event_poll_enabled"):
            if current_status is None:
                should_continue_polling = True
                _log_call("POLL: No status yet, will continue")
            elif current_status not in terminal_statuses:
                should_continue_polling = True
                _log_call(f"POLL: Active status '{current_status}', will continue")
            else:
                _log_call(f"POLL: Terminal status '{current_status}', stopping")
    elif run_id:
        _log_call(f"SKIP polling: is_sending={st.session_state.get('is_sending')}")
    
    # Render chat
    chat_area = st.empty()
    chat_area.markdown(_render_chat(messages), unsafe_allow_html=True)
    
    # Handle streaming
    if st.session_state.get("pending_message"):
        _log_call("STREAMING: Sending message to chat endpoint")
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
            assistant_message = data.get("assistant_message") or "OK."
            _append_message("assistant", assistant_message)
            run_ref = data.get("run_ref") or {}
            new_run_id = data.get("run_id") or run_ref.get("id")
            if new_run_id:
                if st.session_state.get("run_id") != new_run_id:
                    _reset_run_events(new_run_id)
                st.session_state["run_id"] = new_run_id
                _log_call(f"NEW RUN CREATED: {new_run_id}")
                _refresh_run()
                run_status = run_ref.get("status")
                if run_status == "CREATED":
                    _start_run_background(str(new_run_id))
        else:
            _append_message("assistant", f"❌ Error: {data.get('error')}")
        
        st.session_state["pending_message"] = None
        st.session_state["pending_wallet"] = None
        st.session_state["pending_chain_id"] = None
        st.session_state["is_sending"] = False
        st.session_state["clear_input"] = True
        _log_call("STREAMING: Complete, triggering rerun")
        st.rerun()
    
    # Show current status
    current_events = st.session_state.get("run_events") or []
    if current_events:
        last_event = current_events[-1]
        st.info(f"Current step: {last_event.get('step')} ({last_event.get('status')})")
    
    # Trigger rerun if needed
    if run_id and (new_event or should_continue_polling):
        _log_call(f"RERUN: new_event={new_event}, should_continue={should_continue_polling}")
        time.sleep(0.2)  # Small delay to prevent UI flicker
        st.rerun()
    else:
        _log_call(f"NO RERUN: new_event={new_event}, should_continue={should_continue_polling}")
    
    _log_call("=== RENDER END ===")
    
    # Input area
    st.markdown("### ✍️ Your Message")
    st.text_area(
        "Message",
        key="chat_input",
        placeholder="e.g., Swap 100 USDC to WETH",
        height=100,
        label_visibility="collapsed",
    )
    
    col1, col2 = st.columns([3, 1])
    with col1:
        send_label = "⏳ Sending..." if st.session_state["is_sending"] else "📤 Send"
        st.button(send_label, on_click=_on_send, disabled=st.session_state["is_sending"], use_container_width=True)
    with col2:
        st.button("🗑️ Clear", on_click=_on_clear_chat, use_container_width=True)

with tab_timeline:
    run_data = st.session_state.get("run_data")
    if not run_data:
        st.info("No run data yet. Start a transaction to see the timeline.")
    else:
        run_payload = _get_run_payload(run_data)
        status = run_payload.get("status") or "UNKNOWN"
        st.markdown(f"**Status:** `{status}`")
        
        timeline = st.session_state.get("run_events") or []
        if timeline:
            st.dataframe(timeline, use_container_width=True)
        else:
            st.info("No timeline events yet.")

with tab_debug:
    st.markdown("### Call Log")
    log_text = "\n".join(st.session_state.get("call_log", [])[-50:])
    st.code(log_text, language="text")
    
    if st.button("Clear Log"):
        st.session_state["call_log"] = []
        st.rerun()
    
    st.markdown("---")
    
    if st.session_state.get("show_last_json"):
        router = st.session_state.get("last_router") or {}
        if router:
            st.markdown("### Router Response")
            st.json(router)
        
        run_data = st.session_state.get("run_data")
        if run_data:
            st.markdown("### Run Data")
            run_payload = _get_run_payload(run_data)
            st.json(run_payload)
    
    st.markdown("---")
    st.markdown("### Session State")
    st.json({
        "run_id": st.session_state.get("run_id"),
        "run_events_count": len(st.session_state.get("run_events", [])),
        "run_status_live": st.session_state.get("run_status_live"),
        "is_sending": st.session_state.get("is_sending"),
        "event_poll_enabled": st.session_state.get("event_poll_enabled"),
    })