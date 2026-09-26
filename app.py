import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# Import modularized AI router and database functions
from utils.ai_router import process_sms_with_ai
from utils.database import init_db, save_transactions_to_db, load_transactions_from_db
from components.language_selector import render_language_selector
from components.voice_input import render_voice_input
from localization import get_text

# --- Config & Initialization ---
load_dotenv()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").upper()

# Initialize the SQLite database on startup
init_db()

st.set_page_config(page_title="Biashara Bookkeeper", page_icon="📊", layout="wide")

# Load existing historical data from SQLite into session state on startup
if "ledger_df" not in st.session_state:
    st.session_state["ledger_df"] = load_transactions_from_db()

# --- Sidebar ---
with st.sidebar:
    language = render_language_selector()
    st.header(f"⚙️ {get_text('settings', language)}")
    st.info(
        f"**{get_text('active_ai', language)}:** {MODEL_PROVIDER}\n\n"
        f"*{get_text('change_provider', language)}*"
    )
    st.markdown("---")
    st.markdown(f"### 💡 {get_text('tips', language)}")
    st.markdown(
        f"- {get_text('tip_paste', language)}\n"
        f"- {get_text('tip_ai', language)}"
    )

# --- Main Header ---
st.title(f"📊 {get_text('app_title', language)}")
st.markdown(get_text("tagline", language))
st.divider()

# --- Application Layout (Tabs) ---
tab_ledger, tab_analytics = st.tabs(
    [
        f"📝 {get_text('ledger_tab', language)}",
        f"📈 {get_text('analytics_tab', language)}",
    ]
)

with tab_ledger:
    col_input, col_results = st.columns([1, 2], gap="large")

    with col_input:
        st.subheader(get_text("input_data", language))
        transcript = render_voice_input(language)
        if transcript:
            st.session_state["sms_input"] = transcript
        sms_input = st.text_area(
            get_text("sms_label", language),
            height=300,
            placeholder=get_text("sms_placeholder", language),
            key="sms_input",
        )
        submit_btn = st.button(
            f"{get_text('process_receipts', language)} 🚀",
            type="primary",
            use_container_width=True,
        )

    with col_results:
        st.subheader(get_text("generated_ledger", language))
        
        if submit_btn:
            if not sms_input.strip():
                st.warning(f"⚠️ {get_text('empty_message', language)}")
            else:
                with st.spinner(get_text("analyzing", language, provider=MODEL_PROVIDER)):
                    try:
                        # Call modularized function from utils/ai_router.py
                        data_list = process_sms_with_ai(sms_input, MODEL_PROVIDER)
                        
                        df = pd.DataFrame(data_list)
                        
                        # Save DataFrame permanently to SQLite Database
                        save_transactions_to_db(df)
                        
                        # Reload full history from DB into session state
                        st.session_state["ledger_df"] = load_transactions_from_db()
                        
                        # --- Render Ledger ---
                        current_df = st.session_state["ledger_df"]
                        st.dataframe(current_df, use_container_width=True, hide_index=True)
                        
                        if "Amount" in current_df.columns:
                            total = pd.to_numeric(current_df["Amount"], errors="coerce").sum()
                            
                            m_col1, m_col2 = st.columns(2)
                            m_col1.metric(
                                label=get_text("tracked_amount", language),
                                value=f"KES {total:,.2f}",
                            )
                            
                            csv_data = current_df.to_csv(index=False).encode('utf-8')
                            m_col2.download_button(
                                label=f"📥 {get_text('download_csv', language)}",
                                data=csv_data,
                                file_name="mpesa_daily_ledger.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        
                    except Exception as e:
                        st.error(get_text("processing_error", language, error=str(e)))
        else:
            # Render from session state / database history
            if "ledger_df" in st.session_state and not st.session_state["ledger_df"].empty:
                df = st.session_state["ledger_df"]
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                if "Amount" in df.columns:
                    total = pd.to_numeric(df["Amount"], errors="coerce").sum()
                    m_col1, m_col2 = st.columns(2)
                    m_col1.metric(
                        label=get_text("tracked_amount", language),
                        value=f"KES {total:,.2f}",
                    )
                    
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    m_col2.download_button(
                        label=f"📥 {get_text('download_csv', language)}",
                        data=csv_data,
                        file_name="mpesa_daily_ledger.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            else:
                st.info(get_text("awaiting_input", language))

with tab_analytics:
    st.title(f"📈 {get_text('analytics_title', language)}")
    st.markdown(get_text("analytics_description", language))
    st.divider()

    # Check if ledger data exists in session state / database
    if "ledger_df" in st.session_state and not st.session_state["ledger_df"].empty:
        analytics_df = st.session_state["ledger_df"].copy()
        
        # Ensure Amount is treated numerically for aggregations
        analytics_df["Amount"] = pd.to_numeric(analytics_df["Amount"], errors="coerce")

        col_metric1, col_metric2 = st.columns(2)
        with col_metric1:
            total_sum = analytics_df["Amount"].sum()
            st.metric(label=get_text("overall_amount", language), value=f"KES {total_sum:,.2f}")
        with col_metric2:
            total_count = len(analytics_df)
            st.metric(label=get_text("transaction_count", language), value=total_count)

        st.markdown(f"### 📊 {get_text('category_totals', language)}")
        
        if "Category" in analytics_df.columns and "Amount" in analytics_df.columns:
            # Group data by category and sum the amounts
            category_group = analytics_df.groupby("Category")["Amount"].sum()
            
            # Render a native Streamlit bar chart
            st.bar_chart(category_group)
        else:
            st.warning(get_text("missing_columns", language))
            
    else:
        st.info(f"ℹ️ {get_text('no_transactions', language)}")