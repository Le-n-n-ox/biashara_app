import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Database & Utilities
from database import init_db, load_transactions_from_db, save_transactions_to_db
from utils.fraud_detector import analyze_mpesa_fraud
from utils.parsing import process_receipt_pipeline, process_with_ai

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

# --- Main App Execution ---
selected_label, selected_provider = render_sidebar(AI_PROVIDERS, DEFAULT_PROVIDER_LABEL)

st.title("📘 Biashara Bookkeeper")
st.markdown("Automated M-Pesa intelligence for the modern Kenyan business.")

with st.expander("📥 Add New Transactions (Paste M-Pesa SMS)", expanded=True):
    raw_sms = st.text_area("M-Pesa SMS Input", height=180, placeholder="Paste your raw messages here...", label_visibility="collapsed")
    
    # Use columns to make the button look more balanced under the text area
    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        process_button = st.button("Analyze Receipts 🚀", type="primary", use_container_width=True)
if process_button:
    if not raw_sms.strip(): st.warning("⚠️ Please paste at least one SMS receipt first.")
    else:
        receipt_lines = [line for line in raw_sms.splitlines() if re.match(r"^[A-Z0-9]{8,12}\b", line.strip())]
        checks = [analyze_mpesa_fraud(line) for line in receipt_lines]
        safe_lines = [line for line, check in zip(receipt_lines, checks) if not check["is_suspicious"]]
        blocked_checks = [check for check in checks if check["is_suspicious"]]

        if blocked_checks:
            st.error(blocked_checks[0]["reason"])
            st.warning(f"🛡️ Security Block: Prevented {len(blocked_checks)} suspicious receipt(s).")

        if not safe_lines: st.info("No safe receipts were available to add to the ledger.")
        else:
            safe_sms = "\n".join(safe_lines)
            try:
                with st.spinner(f"Processing with {selected_label}..."): transactions = process_with_ai(safe_sms, selected_provider)
            except Exception as error:
                transactions = process_receipt_pipeline(safe_sms)
                st.warning(f"AI processing failed; used the local parser instead. Details: {error}")

            new_df = pd.DataFrame(transactions)
            existing_df = load_transactions_from_db()
            if not new_df.empty:
                if not existing_df.empty: new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]
                new_df = new_df.drop_duplicates(subset=["Transaction Code"])
                if not new_df.empty:
                    save_transactions_to_db(new_df)
                    st.success(f"✅ Successfully registered {len(new_df)} new transaction(s).")
                    st.rerun()

            if new_df.empty: st.info("ℹ️ No new receipts found.")

st.divider()

# Fetch data and render the components
df = load_transactions_from_db()
render_financial_metrics(df)
render_ledger_and_analytics(df)