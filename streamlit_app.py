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


def _inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --primary-light: #818cf8;
  --primary-glow: rgba(99, 102, 241, 0.15);
  --success: #10b981;
  --success-light: #d1fae5;
  --warning: #f59e0b;
  --warning-light: #fef3c7;
  --danger: #ef4444;
  --danger-light: #fee2e2;
  --info: #3b82f6;
  --info-light: #dbeafe;
  --bg-primary: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-tertiary: #f1f5f9;
  --bg-chat: #fafbfc;
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-tertiary: #94a3b8;
  --border: #e2e8f0;
  --border-light: #f1f5f9;
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --radius-full: 9999px;
}

* {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

html, body, [class*="stApp"] {
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  color: var(--text-primary);
}

#MainMenu, footer, header {
  visibility: hidden;
}

.block-container {
  padding: 1.5rem 2rem 3rem 2rem;
  max-width: 1400px;
}

/* Header with glassmorphism */
.nexora-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: var(--radius-xl);
  padding: 2.5rem;
  margin-bottom: 2rem;
  box-shadow: var(--shadow-xl), 0 0 40px rgba(102, 126, 234, 0.3);
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.nexora-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(circle at 20% 50%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, rgba(255, 255, 255, 0.08) 0%, transparent 50%);
  pointer-events: none;
}

.nexora-header h1 {
  color: white;
  font-size: 2.75rem;
  font-weight: 800;
  margin: 0 0 0.5rem 0;
  position: relative;
  z-index: 1;
  letter-spacing: -0.02em;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.nexora-header p {
  color: rgba(255, 255, 255, 0.95);
  font-size: 1.125rem;
  margin: 0;
  position: relative;
  z-index: 1;
  font-weight: 400;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-full);
  font-size: 0.875rem;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  position: relative;
  z-index: 1;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  box-shadow: 0 0 8px currentColor;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(0.95);
  }
}

/* Enhanced Cards */
.card {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.5rem;
  box-shadow: var(--shadow-sm);
  margin-bottom: 1.25rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--border);
}

.card-header {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.625rem;
  letter-spacing: -0.01em;
}

/* Enhanced Chat Container */
.chat-container {
  background: var(--bg-chat);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 1.5rem;
  min-height: 400px;
  max-height: 600px;
  overflow-y: auto;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
  margin-bottom: 1.5rem;
  position: relative;
}

.chat-container::-webkit-scrollbar {
  width: 10px;
}

.chat-container::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px;
}

.chat-container::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-full);
  border: 2px solid var(--bg-chat);
}

.chat-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* Enhanced Messages */
.message {
  display: flex;
  margin-bottom: 1.5rem;
  animation: slideUp 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 75%;
  padding: 1rem 1.25rem;
  border-radius: var(--radius-lg);
  white-space: pre-wrap;
  line-height: 1.6;
  position: relative;
  font-size: 0.9375rem;
}

.message.user .message-bubble {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
  border-bottom-right-radius: 4px;
  box-shadow: var(--shadow-md), 0 0 20px var(--primary-glow);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.message.assistant .message-bubble {
  background: white;
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.message-time {
  font-size: 0.75rem;
  opacity: 0.7;
  margin-top: 0.5rem;
  font-weight: 500;
}

/* Enhanced Mode Pills */
.mode-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.125rem;
  border-radius: var(--radius-full);
  font-size: 0.875rem;
  font-weight: 600;
  margin: 0.75rem 0;
  box-shadow: var(--shadow-sm);
  transition: all 0.3s ease;
}

.mode-pill:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.mode-pill.query {
  background: linear-gradient(135deg, var(--info-light) 0%, #bfdbfe 100%);
  color: #1e40af;
  border: 1px solid #93c5fd;
}

.mode-pill.clarify {
  background: linear-gradient(135deg, var(--warning-light) 0%, #fdba74 100%);
  color: #9a3412;
  border: 1px solid #fb923c;
}

.mode-pill.action {
  background: linear-gradient(135deg, #e9d5ff 0%, #d8b4fe 100%);
  color: #6b21a8;
  border: 1px solid #c084fc;
}

.mode-pill.general {
  background: linear-gradient(135deg, var(--bg-tertiary) 0%, #e2e8f0 100%);
  color: var(--text-primary);
  border: 1px solid #cbd5e1;
}

/* Enhanced Buttons */
.stButton > button {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
  border: none;
  padding: 0.875rem 1.75rem;
  border-radius: var(--radius-full);
  font-weight: 600;
  font-size: 0.9375rem;
  letter-spacing: 0.01em;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-md), 0 0 20px var(--primary-glow);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.stButton > button::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s;
}

.stButton > button:hover::before {
  left: 100%;
}

.stButton > button:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg), 0 0 30px var(--primary-glow);
  background: linear-gradient(135deg, var(--primary-light) 0%, var(--primary) 100%);
}

.stButton > button:active {
  transform: translateY(0);
  box-shadow: var(--shadow-sm);
}

.stButton > button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: var(--shadow-sm) !important;
}

/* Enhanced Input Fields */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > select {
  background: var(--bg-primary);
  border: 2px solid var(--border);
  border-radius: var(--radius-md);
  padding: 0.875rem 1.125rem;
  font-size: 0.9375rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--text-primary);
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stSelectbox > div > div > select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 4px var(--primary-glow), var(--shadow-sm);
  outline: none;
  background: white;
}

.stTextArea > div > div > textarea {
  min-height: 100px;
  resize: vertical;
}

/* Enhanced Tabs */
.stTabs {
  margin-top: 0.5rem;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 0.75rem;
  background: var(--bg-primary);
  padding: 0.625rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.stTabs [data-baseweb="tab"] {
  padding: 0.875rem 1.5rem;
  border-radius: var(--radius-sm);
  font-weight: 600;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--text-secondary);
  font-size: 0.9375rem;
}

.stTabs [data-baseweb="tab"]:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
  box-shadow: var(--shadow-sm), 0 0 15px var(--primary-glow);
}

/* Quick Action Cards */
.quick-action-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-top: 1rem;
}

.quick-action {
  background: linear-gradient(135deg, white 0%, var(--bg-tertiary) 100%);
  border: 2px solid var(--border);
  padding: 1.25rem;
  border-radius: var(--radius-md);
  text-align: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.9375rem;
}

.quick-action:hover {
  border-color: var(--primary);
  background: linear-gradient(135deg, white 0%, var(--primary-glow) 100%);
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

/* Chips */
.chip {
  display: inline-block;
  padding: 0.5rem 0.875rem;
  margin: 0.25rem;
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
  font-size: 0.8125rem;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  font-weight: 500;
  transition: all 0.2s ease;
}

.chip:hover {
  background: var(--bg-primary);
  border-color: var(--primary);
  color: var(--primary);
}

/* Sidebar Enhancement */
.css-1d391kg, [data-testid="stSidebar"] {
  background: var(--bg-primary);
  border-right: 1px solid var(--border);
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.05);
}

/* Status Indicators */
.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-full);
  font-size: 0.875rem;
  font-weight: 600;
  border: 2px solid;
}

.status-indicator.awaiting {
  background: var(--warning-light);
  border-color: var(--warning);
  color: #78350f;
}

.status-indicator.approved {
  background: var(--success-light);
  border-color: var(--success);
  color: #065f46;
}

.status-indicator.blocked {
  background: var(--danger-light);
  border-color: var(--danger);
  color: #991b1b;
}

/* Loading Animation */
.loading-dots {
  display: inline-flex;
  gap: 0.25rem;
}

.loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* Expander Enhancement */
.streamlit-expanderHeader {
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  font-weight: 600;
  padding: 1rem;
  border: 1px solid var(--border);
  transition: all 0.3s ease;
}

.streamlit-expanderHeader:hover {
  background: var(--bg-primary);
  border-color: var(--primary);
}

/* Info/Warning/Error Boxes */
.stAlert {
  border-radius: var(--radius-md);
  border-left-width: 4px;
  box-shadow: var(--shadow-sm);
}

/* Dark Mode */
@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #1e293b;
    --bg-secondary: #0f172a;
    --bg-tertiary: #334155;
    --bg-chat: #1a2332;
    --text-primary: #f1f5f9;
    --text-secondary: #cbd5e1;
    --text-tertiary: #94a3b8;
    --border: #334155;
    --border-light: #2d3748;
  }
  
  html, body, [class*="stApp"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
  }
  
  .message.assistant .message-bubble {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border-color: var(--border);
  }
  
  .card {
    background: var(--bg-tertiary);
    border-color: var(--border);
  }
  
  .quick-action {
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%);
  }
}

/* Responsive Design */
@media (max-width: 768px) {
  .nexora-header h1 {
    font-size: 2rem;
  }
  
  .header-row {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .message-bubble {
    max-width: 85%;
  }
  
  .quick-action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


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
    st.session_state.setdefault("last_event_poll", 0.0)
    st.session_state.setdefault("event_poll_enabled", True)
    st.session_state.setdefault("call_log", [])


def _log_call(message: str) -> None:
    try:
        ts = time.strftime("%H:%M:%S")
        entry = f"{ts} | {message}"
        if "call_log" in st.session_state:
            st.session_state["call_log"].append(entry)
            if len(st.session_state["call_log"]) > 60:
                st.session_state["call_log"] = st.session_state["call_log"][-60:]
        else:
            print(entry)
    except Exception:
        try:
            print(entry)
        except Exception:
            return


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
        return False
    
    if st.session_state.get("run_events_run_id") != run_id:
        _reset_run_events(run_id)
    
    added = False
    resp = None
    
    try:
        _log_call(f"GET /v1/runs/{run_id}/events (SSE)")
        
        # Use longer timeout for SSE - server may keep connection open
        resp = requests.get(
            f"{st.session_state['base_url']}/v1/runs/{run_id}/events",
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=(5, 30),  # 5s to connect, 30s to read
        )
        
        if resp.status_code >= 400:
            _log_call(f"ERR {resp.status_code} /v1/runs/{run_id}/events")
            return False
        
        _log_call(f"OK {resp.status_code} /v1/runs/{run_id}/events - streaming")
        
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
        _log_call(f"TIMEOUT /v1/runs/{run_id}/events: {exc}")
        return False
    except requests.exceptions.ChunkedEncodingError as exc:
        # This can happen when the connection closes - may be normal
        _log_call(f"CHUNKED ENCODING ERROR (connection closed): {exc}")
    except requests.RequestException as exc:
        _log_call(f"EXC /v1/runs/{run_id}/events: {exc}")
    except Exception as exc:
        _log_call(f"UNEXPECTED EXC in event loop: {exc}")
    finally:
        # Always close the connection
        if resp:
            try:
                resp.close()
                _log_call(f"CLOSED SSE connection for run {run_id}")
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

_inject_styles()

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    
    with st.expander("🔗 Backend Settings", expanded=True):
        st.text_input("Backend URL", key="base_url", help="API endpoint URL")
        
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
                st.session_state["pending_wallet"] = None
                st.session_state["pending_chain_id"] = None
                st.session_state["is_sending"] = False
                st.session_state["clear_input"] = True
                _reset_run_events(None)
                st.rerun()
    
    with st.expander("👛 Wallet & Network", expanded=True):
        st.text_input("Wallet Address", key="wallet_address", placeholder="0x...")
        wallet_value = st.session_state.get("wallet_address")
        if wallet_value and not _is_valid_wallet_address(wallet_value):
            st.warning("⚠️ Invalid wallet address format")
        
        st.selectbox("Network", list(CHAIN_OPTIONS.keys()), key="chain_label")
    
    if st.session_state.get("run_id"):
        st.markdown("---")
        st.markdown("### 🎯 Run Controls")
        st.text_input("Run ID", value=st.session_state.get("run_id"), disabled=True, key="run_id_display")
        
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
    st.checkbox("🔍 Show Debug JSON", key="show_last_json")
    
    with st.expander("🔧 Advanced", expanded=False):
        st.text_input("Conversation ID", key="conversation_id")

# Header
health_ok, _ = _api_request("GET", f"{st.session_state['base_url']}/healthz")
status_text = "Connected" if health_ok else "Disconnected"

st.markdown(
    f"""
    <div class="nexora-header">
        <div class="header-row">
            <div>
                <h1>🔮 Nexora</h1>
                <p>Web3 Intent Copilot - Safe, Explainable Blockchain Actions</p>
            </div>
            <div class="status-badge">
                <span class="status-dot"></span>
                {status_text}
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Main Tabs
tab_chat, tab_timeline, tab_artifacts = st.tabs(["💬 Chat", "📊 Run Timeline", "🔧 Artifacts & Debug"])

with tab_chat:
    # Welcome screen
    if not st.session_state["messages"]:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">👋 Welcome to Nexora</div>
                <p style="color: var(--text-secondary); margin-bottom: 1.5rem; font-size: 0.9375rem;">
                    Your intelligent copilot for safe Web3 transactions. Try one of these examples to get started:
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        samples = [
            ("🪙 Check supported tokens", "Check supported tokens"),
            ("📸 Show wallet snapshot", "Show wallet snapshot"),
            ("🔄 Swap 1 USDC to WETH", "Swap 1 USDC to WETH"),
        ]
        
        cols = st.columns(3)
        for idx, (label, text) in enumerate(samples):
            with cols[idx]:
                if st.button(label, key=f"sample_{idx}", use_container_width=True):
                    wallet_value = st.session_state.get("wallet_address") or None
                    wallet = wallet_value if _is_valid_wallet_address(wallet_value) else None
                    chain_label = st.session_state.get("chain_label")
                    chain_id = CHAIN_OPTIONS.get(chain_label)
                    _queue_chat(text, wallet, chain_id)
                    st.rerun()
    
    # Chat messages
    messages = st.session_state["messages"]
    run_id = st.session_state.get("run_id")
    
    # Poll for events if we have an active run
    new_event = False
    if run_id:
        new_event = _consume_run_events(str(run_id))
        
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
        now = time.time()
        
        # Poll more frequently when run is active (not in terminal state)
        if (st.session_state.get("event_poll_enabled") 
            and current_status 
            and current_status not in terminal_statuses):
            
            last_poll = st.session_state.get("last_event_poll", 0.0)
            # Poll every 0.5 seconds when active
            if now - last_poll > 0.5:
                st.session_state["last_event_poll"] = now
                # Small sleep to prevent UI flickering
                time.sleep(0.2)
                st.rerun()
    
    chat_area = st.empty()
    chat_area.markdown(_render_chat(messages), unsafe_allow_html=True)
    
    # Handle streaming
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
            assistant_message = data.get("assistant_message") or "OK."
            _append_message("assistant", assistant_message)
            run_ref = data.get("run_ref") or {}
            run_id = data.get("run_id") or run_ref.get("id")
            if run_id:
                if st.session_state.get("run_id") != run_id:
                    _reset_run_events(run_id)
                st.session_state["run_id"] = run_id
                _refresh_run()
                run_status = run_ref.get("status")
                if run_status == "CREATED":
                    _start_run_background(str(run_id))
        else:
            _append_message("assistant", f"❌ Error: {data.get('error')}")
        
        st.session_state["pending_message"] = None
        st.session_state["pending_wallet"] = None
        st.session_state["pending_chain_id"] = None
        st.session_state["is_sending"] = False
        st.session_state["clear_input"] = True
        st.rerun()
    
    # Mode indicator and suggestions
    router = st.session_state.get("last_router") or {}
    if router:
        mode_value = router.get("mode") or "CLARIFY"
        mode_labels = {
            "QUERY": ("🔍 Answering question", "query"),
            "CLARIFY": ("❓ Need more details", "clarify"),
            "ACTION": ("⚡ Preparing transaction", "action"),
            "GENERAL": ("💬 General chat", "general"),
        }
        label, css_class = mode_labels.get(mode_value, ("💬 Ready", "general"))
        
        st.markdown(
            f"<div class='mode-pill {css_class}'>{label}</div>",
            unsafe_allow_html=True,
        )

        current_events = st.session_state.get("run_events") or []
        if current_events:
            last_event = current_events[-1]
            step_name = last_event.get("step") or "UNKNOWN"
            step_status = last_event.get("status") or "UNKNOWN"
            st.caption(f"Current step: {step_name} ({step_status})")
        
        # Suggestions
        suggestions = router.get("suggestions") or []
        if suggestions and mode_value == "GENERAL":
            st.markdown("**💡 Suggested actions:**")
            cols = st.columns(min(3, len(suggestions)))
            for idx, suggestion in enumerate(suggestions):
                with cols[idx % len(cols)]:
                    if st.button(suggestion, key=f"suggest_{idx}", use_container_width=True):
                        wallet_value = st.session_state.get("wallet_address") or None
                        wallet = wallet_value if _is_valid_wallet_address(wallet_value) else None
                        chain_label = st.session_state.get("chain_label")
                        chain_id = CHAIN_OPTIONS.get(chain_label)
                        _queue_chat(suggestion, wallet, chain_id)
                        st.rerun()
        
        # Debug info
        if st.session_state.get("show_last_json"):
            with st.expander("🐛 Debug: Intent Router", expanded=False):
                intent_type = (router.get("classification") or {}).get("intent_type")
                missing = (router.get("classification") or {}).get("missing_slots") or []
                
                st.markdown(f"**Mode:** `{mode_value}`")
                st.markdown(f"**Intent Type:** `{intent_type or 'n/a'}`")
                
                if missing:
                    st.markdown("**Missing slots:**")
                    st.markdown(
                        " ".join([f"<span class='chip'>{_escape(slot)}</span>" for slot in missing]),
                        unsafe_allow_html=True,
                    )
                
                st.json(router)
                st.markdown("**Call log**")
                st.code("\n".join(st.session_state.get("call_log", [])))

    # Trigger rerun if we got new events
    if run_id and new_event and not st.session_state.get("pending_message"):
        st.rerun()
    
    # Input area
    st.markdown("### ✍️ Your Message")
    st.text_area(
        "What would you like to do?",
        key="chat_input",
        placeholder="e.g., Swap 100 USDC to WETH\nWhat tokens are supported?\nShow my wallet balance",
        height=100,
        label_visibility="collapsed",
    )
    
    col_send, col_clear = st.columns([3, 1])
    with col_send:
        send_label = "⏳ Sending..." if st.session_state["is_sending"] else "📤 Send Message"
        st.button(
            send_label,
            on_click=_on_send,
            disabled=st.session_state["is_sending"],
            use_container_width=True,
            type="primary"
        )
    with col_clear:
        st.button("🗑️ Clear", on_click=_on_clear_chat, use_container_width=True)

with tab_timeline:
    run_data = st.session_state.get("run_data")
    if not run_data:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">📊 Run Timeline</div>
                <p style="color: var(--text-secondary); font-size: 0.9375rem;">
                    No run data available yet. Start a transaction to see the execution timeline.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        run_payload = _get_run_payload(run_data)
        status = run_payload.get("status") or "UNKNOWN"
        run_id = st.session_state.get("run_id")
        if run_id:
            _consume_run_events(str(run_id))
        
        # Status card with visual indicator
        status_icons = {
            "AWAITING_APPROVAL": ("⏳", "awaiting"),
            "APPROVED": ("✅", "approved"),
            "BLOCKED": ("⛔", "blocked"),
            "COMPLETED": ("✅", "approved"),
            "FAILED": ("❌", "blocked"),
        }
        icon, status_class = status_icons.get(status, ("ℹ️", "general"))
        
        st.markdown(
            f"""
            <div class="card">
                <div class="card-header">📊 Run Status</div>
                <div class="status-indicator {status_class}">
                    <span>{icon}</span>
                    <span>{status}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        if status == "AWAITING_APPROVAL":
            st.warning("⏳ This run requires your approval before execution. Use the sidebar controls to approve.")
        
        # Timeline
        timeline = st.session_state.get("run_events") or (run_payload.get("artifacts") or {}).get("timeline") or []
        if timeline:
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">📋 Execution Timeline</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.dataframe(
                timeline,
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("ℹ️ No timeline entries generated yet.")

with tab_artifacts:
    run_data = st.session_state.get("run_data")
    if not run_data:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">🔧 Artifacts & Debug</div>
                <p style="color: var(--text-secondary); font-size: 0.9375rem;">
                    No artifacts available yet. Start a transaction to see detailed execution information.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        run_payload = _get_run_payload(run_data)
        artifacts = run_payload.get("artifacts") or {}
        
        artifact_sections = [
            ("📝 Transaction Plan", "tx_plan"),
            ("📤 Transaction Requests", "tx_requests"),
            ("🔬 Simulation Results", "simulation"),
            ("🛡️ Policy Evaluation", "policy_result"),
            ("🔒 Security Analysis", "security_result"),
            ("⚖️ Judge Decision", "judge_result"),
            ("✅ Final Decision", "decision"),
        ]
        
        has_artifacts = False
        for title, key in artifact_sections:
            if key in artifacts and artifacts.get(key) not in (None, {}, []):
                has_artifacts = True
                with st.expander(title, expanded=False):
                    st.json(artifacts.get(key))
        
        if not has_artifacts:
            st.info("ℹ️ No artifacts generated yet.")
        
        # Execute response
        if st.session_state.get("last_execute"):
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">🚀 Execution Response</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.json(st.session_state.get("last_execute"))
        
        # Download button
        if run_data:
            run_id = run_payload.get("id", "unknown")
            st.download_button(
                "📥 Download Complete Run Data (JSON)",
                data=json.dumps(run_data, indent=2),
                file_name=f"nexora_run_{run_id}.json",
                mime="application/json",
                use_container_width=True,
                type="primary"
            )