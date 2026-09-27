import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from utils.theme import apply_theme, render_theme_toggle
from utils.auth import render_auth_gate


# Database & Utilities
from database import init_db, load_transactions_from_db, save_transactions_to_db
from utils.fraud_detector import analyze_mpesa_fraud
from utils.parsing import process_receipt_pipeline, process_with_ai
from utils.voice import transcribe_audio
from localization.translations import current_language, speech_language, tr
from localization.translations import LANGUAGES
from streamlit_mic_recorder import mic_recorder

# UI Components
from components.sidebar import render_sidebar
from components.metrics import render_financial_metrics
from components.tabs import render_ledger_and_analytics

load_dotenv()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").strip().upper()
AI_PROVIDERS = {
    "Ollama": "OLLAMA",
    "Google Gemini": "GEMINI",
    "NVIDIA Brev API": "NVIDIA",
    "OpenAI": "OPENAI",
}
DEFAULT_PROVIDER_LABEL = next((label for label, p in AI_PROVIDERS.items() if p == MODEL_PROVIDER), "Ollama")

init_db()
st.set_page_config(page_title="Biashara Bookkeeper", page_icon="📘", layout="wide", initial_sidebar_state="expanded")

# --- Load Custom CSS ---
try:
    with open("assets/styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass


apply_theme()  # must run AFTER styles.css so overrides win the cascade

render_auth_gate()  # blocks here (st.stop) until the user logs in or registers

# --- Main App Execution (only reached once authenticated) ---
current_user_id = st.session_state.user["id"]

# Language is a dashboard setting; keep authentication screens focused.
_, language_col = st.columns([5, 1])
with language_col:
    language_label = st.selectbox(
        "Language / Lugha",
        list(LANGUAGES),
        index=list(LANGUAGES.values()).index(st.session_state.get("language", "en")),
        key="global_language_selector",
        label_visibility="collapsed",
    )
    selected_language = LANGUAGES[language_label]
    if selected_language != st.session_state.get("language", "en"):
        st.session_state.language = selected_language
        st.rerun()

selected_label, selected_provider = render_sidebar(AI_PROVIDERS, DEFAULT_PROVIDER_LABEL, current_user_id)

st.markdown(
    f"""
    <header class="brand-masthead">
        <div class="brand-kicker"><span class="brand-mark">K</span>{tr('brand_kicker')}</div>
        <div class="brand-heading-row">
            <h1>📘 {tr('title')}</h1>
            <span class="ledger-status"><span class="status-dot"></span>{tr('status_ready')}</span>
        </div>
        <p class="brand-subtitle">{tr('subtitle')}</p>
    </header>
    """,
    unsafe_allow_html=True,
)

with st.expander(f"📥 {tr('add_transactions')} · {tr('paste_hint')}", expanded=True):
    if "receipt_input" not in st.session_state:
        st.session_state.receipt_input = ""

    voice_col, input_col = st.columns([1, 2], gap="large")
    with voice_col:
        st.markdown(f"#### 🎙️ {tr('voice_title')}")
        st.caption(tr("voice_caption"))
        st.info(tr("voice_help"), icon=":material/mic:")
        audio_value = mic_recorder(
            start_prompt=tr("record"),
            stop_prompt=tr("stop_recording"),
            just_once=True,
            use_container_width=True,
            format="wav",
            key="receipt_voice_recording",
        )
        if audio_value:
            audio_bytes = audio_value.get("bytes", b"")
            if not audio_bytes:
                st.warning(tr("voice_empty"))
            else:
                st.audio(audio_bytes, format="audio/wav", width="stretch")
                with st.spinner(tr("transcribing")):
                    try:
                        transcript = transcribe_audio(
                            audio_value,
                            speech_language(),
                        )
                        st.session_state.receipt_input = transcript
                        st.success(tr("voice_success"))
                    except RuntimeError:
                        st.warning(tr("voice_unavailable"))
                    except ValueError:
                        st.warning(tr("voice_empty"))
                    except Exception:
                        st.warning(tr("voice_error"))

    with input_col:
        raw_sms = st.text_area(
            tr("sms_input"),
            height=180,
            placeholder=tr("paste_hint"),
            key="receipt_input",
            label_visibility="collapsed",
        )

    # Use columns to make the button look more balanced under the text area
    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        process_button = st.button(f"{tr('analyze')} 🚀", type="primary", width="stretch")
if process_button:
    if not raw_sms.strip(): st.warning(f"⚠️ {tr('paste_first')}")
    else:
        receipt_lines = [line for line in raw_sms.splitlines() if re.match(r"^[A-Z0-9]{8,12}\b", line.strip())]
        checks = [analyze_mpesa_fraud(line) for line in receipt_lines]
        safe_lines = [line for line, check in zip(receipt_lines, checks) if not check["is_suspicious"]]
        blocked_checks = [check for check in checks if check["is_suspicious"]]

        if blocked_checks:
            st.error(blocked_checks[0]["reason"])
            st.warning(f"Security Block: Prevented {len(blocked_checks)} suspicious receipt(s).")

        if not safe_lines: st.info("No safe receipts were available to add to the ledger.")
        else:
            safe_sms = "\n".join(safe_lines)
            try:
                with st.spinner(f"Processing with {selected_label}..."): transactions = process_with_ai(safe_sms, selected_provider, current_user_id)
            except Exception as error:
                transactions = process_receipt_pipeline(safe_sms)
                st.warning(f"AI processing failed; used the local parser instead. Details: {error}")

            new_df = pd.DataFrame(transactions)
            existing_df = load_transactions_from_db(current_user_id)
            if not new_df.empty:
                if not existing_df.empty: new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]
                new_df = new_df.drop_duplicates(subset=["Transaction Code"])
                if not new_df.empty:
                    save_transactions_to_db(new_df, current_user_id)
                    st.success(f"Successfully registered {len(new_df)} new transaction(s).")
                    st.rerun()

            if new_df.empty: st.info("No new receipts found.")

st.divider()

# Fetch data and render the components
df = load_transactions_from_db(current_user_id)
render_financial_metrics(df)
render_ledger_and_analytics(df)