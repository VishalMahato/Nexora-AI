from __future__ import annotations

import json
import time
import uuid
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
        if method == "GET":
            resp = requests.get(url, timeout=12)
        else:
            resp = requests.post(url, json=payload, timeout=400)
        if resp.status_code >= 400:
            return False, {"error": f"{resp.status_code} {resp.text}"}
        if resp.text.strip() == "":
            return False, {"error": "empty response body"}
        return True, resp.json()
    except requests.RequestException as exc:
        return False, {"error": str(exc)}


def _get_run_payload(run_data: dict[str, Any]) -> dict[str, Any]:
    if "run" in run_data:
        return run_data.get("run") or {}
    return run_data


def _inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --primary-light: #818cf8;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #3b82f6;
  --bg-primary: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-tertiary: #f1f5f9;
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-tertiary: #94a3b8;
  --border: #e2e8f0;
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

* {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

html, body, [class*="stApp"] {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* Hide Streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Container */
.block-container {
  padding: 1rem 2rem 3rem 2rem;
  max-width: 1400px;
}

/* Header */
.nexora-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  padding: 2.5rem;
  margin-bottom: 2rem;
  box-shadow: var(--shadow-xl);
  position: relative;
  overflow: hidden;
}

.nexora-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  opacity: 0.4;
}

.nexora-header h1 {
  color: white;
  font-size: 2.5rem;
  font-weight: 700;
  margin: 0 0 0.5rem 0;
  position: relative;
  z-index: 1;
}

.nexora-header p {
  color: rgba(255, 255, 255, 0.9);
  font-size: 1.1rem;
  margin: 0;
  position: relative;
  z-index: 1;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  margin-top: 1rem;
  position: relative;
  z-index: 1;
}

.status-badge.connected {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
  border: 2px solid rgba(16, 185, 129, 0.3);
}

.status-badge.disconnected {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  border: 2px solid rgba(239, 68, 68, 0.3);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Cards */
.card {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: var(--shadow-sm);
  margin-bottom: 1rem;
  transition: all 0.3s ease;
}

.card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.card-header {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Chat Messages */
.chat-container {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.5rem;
  min-height: 260px;
  max-height: 600px;
  overflow-y: auto;
  box-shadow: var(--shadow-sm);
  margin-bottom: 1rem;
}

.message {
  display: flex;
  margin-bottom: 1.5rem;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
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
  max-width: 70%;
  padding: 1rem 1.25rem;
  border-radius: 18px;
  position: relative;
#   white-space: pre-wrap;
  line-height: 1.5;
}

.message.user .message-bubble {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
  border-bottom-right-radius: 4px;
  box-shadow: var(--shadow-md);
}

.message.assistant .message-bubble {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  border: 1px solid var(--border);
}

.message-time {
  font-size: 0.75rem;
  opacity: 0.7;
  margin-top: 0.5rem;
  text-align: right;
}

/* Mode Pills */
.mode-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  margin: 0.5rem 0;
  box-shadow: var(--shadow-sm);
}

.mode-pill.query { 
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  color: #1e40af;
  border: 1px solid #93c5fd;
}

.mode-pill.clarify { 
  background: linear-gradient(135deg, #fed7aa 0%, #fdba74 100%);
  color: #9a3412;
  border: 1px solid #fb923c;
}

.mode-pill.action { 
  background: linear-gradient(135deg, #e9d5ff 0%, #d8b4fe 100%);
  color: #6b21a8;
  border: 1px solid #c084fc;
}

.mode-pill.general { 
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  color: #0f172a;
  border: 1px solid #cbd5e1;
}

/* Buttons */
.stButton > button {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.95rem;
  transition: all 0.3s ease;
  box-shadow: var(--shadow-md);
  cursor: pointer;
}

.stButton > button:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
  background: linear-gradient(135deg, var(--primary-light) 0%, var(--primary) 100%);
}

.stButton > button:active {
  transform: translateY(0);
}

/* Input Fields */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > select {
  background: var(--bg-primary);
  border: 2px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem 1rem;
  font-size: 0.95rem;
  transition: all 0.3s ease;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stSelectbox > div > div > select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  outline: none;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  gap: 1rem;
  background: var(--bg-primary);
  padding: 0.5rem;
  border-radius: 12px;
  border: 1px solid var(--border);
}

.stTabs [data-baseweb="tab"] {
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-weight: 600;
  transition: all 0.3s ease;
}

.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
}

/* Sidebar */
.css-1d391kg, [data-testid="stSidebar"] {
  background: var(--bg-primary);
  border-right: 1px solid var(--border);
}

/* Expander */
.streamlit-expanderHeader {
  background: var(--bg-tertiary);
  border-radius: 12px;
  font-weight: 600;
  padding: 1rem;
  border: 1px solid var(--border);
}

/* Quick Action Buttons */
.quick-action {
  background: var(--bg-tertiary);
  border: 2px solid var(--border);
  padding: 1rem;
  border-radius: 12px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  font-weight: 500;
}

.quick-action:hover {
  border-color: var(--primary);
  background: var(--bg-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* Chips */
.chip {
  display: inline-block;
  padding: 0.375rem 0.75rem;
  margin: 0.25rem;
  border-radius: 999px;
  background: var(--bg-tertiary);
  font-size: 0.875rem;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  font-weight: 500;
}

/* Loading Spinner */
.loading-spinner {
  display: inline-block;
  width: 20px;
  height: 20px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #1e293b;
    --bg-secondary: #0f172a;
    --bg-tertiary: #334155;
    --text-primary: #f1f5f9;
    --text-secondary: #cbd5e1;
    --text-tertiary: #94a3b8;
    --border: #334155;
  }
  
  .message.assistant .message-bubble {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }
}

/* Scrollbar */
.chat-container::-webkit-scrollbar {
  width: 8px;
}

.chat-container::-webkit-scrollbar-track {
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.chat-container::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}

.chat-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
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


def _append_message(role: str, content: str) -> None:
    ts = time.strftime("%H:%M")
    st.session_state["messages"].append({"role": role, "content": content, "ts": ts})


def _is_valid_wallet_address(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    if not value.startswith("0x"):
        return False
    return len(value) == 42


def _send_chat(message: str, wallet: str | None, chain_id: int | None) -> None:
    if not message.strip():
        return
    if not _is_valid_wallet_address(wallet):
        wallet = None
    history = st.session_state.get("messages", [])[-6:]
    history_payload = [
        {"role": item.get("role"), "content": item.get("content")}
        for item in history
        if item.get("content")
    ]
    _append_message("user", message)
    payload: dict[str, Any] = {
        "message": message,
        "conversation_id": st.session_state["conversation_id"],
        "metadata": {"history": history_payload},
    }
    if wallet:
        payload["wallet_address"] = wallet
    if chain_id:
        payload["chain_id"] = chain_id

    ok, data = _api_request(
        "POST",
        f"{st.session_state['base_url']}/v1/chat/route",
        payload=payload,
    )

    if not ok:
        _append_message("assistant", f"Error: {data.get('error')}")
        return

    st.session_state["last_router"] = data
    assistant_message = data.get("assistant_message") or "OK."
    _append_message("assistant", assistant_message)


    run_ref = data.get("run_ref") or {}
    run_id = data.get("run_id") or run_ref.get("id")
    if run_id:
        st.session_state["run_id"] = run_id
        _refresh_run()


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
        st.success("✅ Execution prepared.")
    else:
        st.error(f"❌ {data.get('error')}")


def _on_send() -> None:
    message = st.session_state.get("chat_input", "")
    wallet_value = st.session_state.get("wallet_address") or None
    wallet = wallet_value if _is_valid_wallet_address(wallet_value) else None
    chain_label = st.session_state.get("chain_label")
    chain_id = CHAIN_OPTIONS.get(chain_label)
    st.session_state["is_sending"] = True
    _send_chat(message, wallet, chain_id)
    st.session_state["chat_input"] = ""
    st.session_state["is_sending"] = False


def _on_clear_chat() -> None:
    st.session_state["messages"] = []
    st.session_state["last_router"] = None
    st.session_state["chat_input"] = ""


# Initialize
_init_state()
st.set_page_config(
    page_title="Nexora - Web3 Intent Copilot",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)
_inject_styles()

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    
    with st.expander("🔗 Backend Settings", expanded=True):
        st.text_input("Backend URL", key="base_url", help="API endpoint URL")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Check", width="stretch"):
                ok, data = _api_request("GET", f"{st.session_state['base_url']}/healthz")
                if ok:
                    st.success("✅ Connected")
                else:
                    st.error(f"❌ {data.get('error')}")
        
        with col2:
            if st.button("🔄 New Chat", width="stretch"):
                st.session_state["conversation_id"] = str(uuid.uuid4())
                st.session_state["messages"] = []
                st.session_state["run_id"] = None
                st.session_state["run_data"] = None
                st.session_state["last_router"] = None
                st.session_state["chat_input"] = ""
                st.rerun()
    
    with st.expander("👛 Wallet & Network", expanded=True):
        st.text_input("Wallet Address", key="wallet_address", placeholder="0x...")
        wallet_value = st.session_state.get("wallet_address")
        if wallet_value and not _is_valid_wallet_address(wallet_value):
            st.warning("Wallet address looks invalid. Use a 0x address with 40 hex characters.")
        st.caption("Format: 0x... (40 hex chars)")
        st.selectbox("Network", list(CHAIN_OPTIONS.keys()), key="chain_label")
    
    if st.session_state.get("run_id"):
        st.markdown("---")
        st.markdown("### 🎯 Run Controls")
        st.text_input("Run ID", value=st.session_state.get("run_id"), disabled=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔄", help="Refresh", width="stretch"):
                _refresh_run()
                st.rerun()
        with col2:
            if st.button("✅", help="Approve", width="stretch"):
                _approve_run()
                st.rerun()
        with col3:
            if st.button("▶️", help="Execute", width="stretch"):
                _execute_run()
                st.rerun()
    
    st.markdown("---")
    st.checkbox("🔍 Show Debug JSON", key="show_last_json")
    
    with st.expander("🔧 Advanced", expanded=False):
        st.text_input("Conversation ID", key="conversation_id")

# Main header
health_ok, _ = _api_request("GET", f"{st.session_state['base_url']}/healthz")
status_class = "connected" if health_ok else "disconnected"
status_text = "Connected" if health_ok else "Disconnected"

st.markdown(
    f"""
    <div class="nexora-header">
        <h1>🔮 Nexora</h1>
        <p>Web3 Intent Copilot - Safe, Explainable Blockchain Actions</p>
        <div class="status-badge {status_class}">
            <div class="status-dot"></div>
            {status_text}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Main tabs
tab_chat, tab_timeline, tab_artifacts = st.tabs(["💬 Chat", "📊 Run Timeline", "🔧 Artifacts & Debug"])

with tab_chat:
    # Welcome screen
    if not st.session_state["messages"]:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">👋 Welcome to Nexora</div>
                <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
                    Your intelligent copilot for safe Web3 transactions. Try one of these to get started:
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        samples = [
            ("🪙 Check supported tokens", "Check supported tokens"),
            ("📸 Show wallet snapshot", "Show wallet snapshot"),
            ("🔄 Swap 1 USDC to WETH", "Swap 1 USDC to WETH")
        ]
        
        cols = st.columns(3)
        for idx, (label, text) in enumerate(samples):
            with cols[idx]:
                st.markdown(f'<div class="quick-action">{label}</div>', unsafe_allow_html=True)
                if st.button(label, key=f"sample_{idx}", width="stretch"):
                    wallet = st.session_state.get("wallet_address") or None
                    chain_label = st.session_state.get("chain_label")
                    chain_id = CHAIN_OPTIONS.get(chain_label)
                    _send_chat(text, wallet, chain_id)
                    st.rerun()
    
    # Chat messages
    chat_parts = ["<div class='chat-container'>"]
    for msg in st.session_state["messages"]: 
        role = msg.get("role", "assistant")
        content = _escape(msg.get("content", "")).replace("\n", "<br/>")
        ts = _escape(msg.get("ts", ""))
        chat_parts.append(
            f"<div class='message {role}'><div class='message-bubble'>{content}<div class='message-time'>{ts}</div></div></div>"
        )
    chat_parts.append("</div>")
    st.markdown("".join(chat_parts), unsafe_allow_html=True)

    # Mode indicator
    router = st.session_state.get("last_router") or {}
    if router:
        mode_value = router.get("mode") or "CLARIFY"
        mode_labels = {
            "QUERY": ("🔍", "Answering a question", "query"),
            "CLARIFY": ("❓", "Waiting for more details", "clarify"),
            "ACTION": ("⚡", "Preparing transaction", "action"),
            "GENERAL": ("💬", "General conversation", "general"),
        }
        icon, label, css_class = mode_labels.get(mode_value, ("💬", "Ready", "general"))
        
        st.markdown(
            f'<div class="mode-pill {css_class}">{icon} {label}</div>',
            unsafe_allow_html=True,
        )
        
        # Suggestions
        suggestions = router.get("suggestions") or []
        if suggestions and mode_value == "GENERAL":
            st.markdown("**💡 Suggestions:**")
            cols = st.columns(min(3, len(suggestions)))
            for idx, suggestion in enumerate(suggestions):
                with cols[idx % len(cols)]:
                    if st.button(suggestion, key=f"suggest_{idx}", width="stretch"):
                        wallet = st.session_state.get("wallet_address") or None
                        chain_label = st.session_state.get("chain_label")
                        chain_id = CHAIN_OPTIONS.get(chain_label)
                        _send_chat(suggestion, wallet, chain_id)
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
    
    # Input area
    st.markdown("### ✍️ Your Message")
    st.text_area(
        "What would you like to do?",
        key="chat_input",
        placeholder="e.g., Swap 100 USDC to WETH\nWhat tokens are supported?",
        height=100,
        label_visibility="collapsed"
    )
    
    col_send, col_clear = st.columns([3, 1])
    with col_send:
        send_label = "Sending..." if st.session_state["is_sending"] else "Send Message"
        st.button(
            send_label,
            on_click=_on_send,
            disabled=st.session_state["is_sending"],
            width="stretch"
        )
    with col_clear:
        st.button("Clear Chat", on_click=_on_clear_chat, width="stretch")

with tab_timeline:
    run_data = st.session_state.get("run_data")
    if not run_data:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">📊 Run Timeline</div>
                <p style="color: var(--text-secondary);">No run data available yet. Start a transaction to see the timeline.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        run_payload = _get_run_payload(run_data)
        status = run_payload.get("status")
        
        # Status card
        status_colors = {
            "AWAITING_APPROVAL": ("warning", "⏳"),
            "APPROVED": ("success", "✅"),
            "EXECUTING": ("info", "🔄"),
            "COMPLETED": ("success", "✅"),
            "BLOCKED": ("danger", "⛔"),
            "FAILED": ("danger", "❌"),
        }
        color, icon = status_colors.get(status, ("info", "ℹ️"))
        
        st.markdown(
            f"""
            <div class="card">
                <div class="card-header">{icon} Run Status</div>
                <p style="font-size: 1.2rem; font-weight: 600; color: var(--{color});">{status or 'UNKNOWN'}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        if status == "AWAITING_APPROVAL":
            st.warning("⏳ This run requires your approval before execution.")
        
        # Timeline
        timeline = (run_payload.get("artifacts") or {}).get("timeline") or []
        if timeline:
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">📋 Timeline Events</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.dataframe(timeline, width="stretch", hide_index=True)
        else:
            st.info("No timeline entries yet.")

with tab_artifacts:
    run_data = st.session_state.get("run_data")
    if not run_data:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">🔧 Artifacts & Debug</div>
                <p style="color: var(--text-secondary);">No artifacts available yet. Start a transaction to see detailed information.</p>
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
            st.info("No artifacts generated yet.")
        
        # Execute response
        if st.session_state.get("last_execute"):
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">🚀 Execute Response</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.json(st.session_state.get("last_execute"))
        
        # Download button
        if run_data:
            run_id = run_payload.get("id", "unknown")
            st.download_button(
                "📥 Download Run JSON",
                data=json.dumps(run_data, indent=2),
                file_name=f"run_{run_id}.json",
                mime="application/json",
                width="stretch"
            )
