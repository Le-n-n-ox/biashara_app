import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# Import modularized AI router and database functions
from utils.ai_router import process_sms_with_ai
from utils.database import init_db, save_transactions_to_db, load_transactions_from_db

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
    st.header("⚙️ Settings")
    st.info(f"**Active AI:** {MODEL_PROVIDER}\n\n*Change `MODEL_PROVIDER` in your `.env` to switch.*")
    st.markdown("---")
    st.markdown("### 💡 Tips")
    st.markdown("- Paste raw SMS text exactly as received.\n- The AI will automatically clean and categorize the data.")

# --- Main Header ---
st.title("📊 Biashara Bookkeeper")
st.markdown("Transform your raw M-Pesa messages into a structured financial ledger in seconds.")
st.divider()

# --- Application Layout (Tabs) ---
tab_ledger, tab_analytics = st.tabs(["📝 Data Entry & Ledger", "📈 Analytics Dashboard"])

with tab_ledger:
    col_input, col_results = st.columns([1, 2], gap="large")

    with col_input:
        st.subheader("1. Input Data")
        sms_input = st.text_area(
            "Paste M-Pesa SMS Receipts:", 
            height=300, 
            placeholder="Ksh1,500.00 paid to QUICKMART SUPERMARKET on 27/9/26..."
        )
        submit_btn = st.button("Process Receipts 🚀", type="primary", use_container_width=True)

    with col_results:
        st.subheader("2. Generated Ledger")
        
        if submit_btn:
            if not sms_input.strip():
                st.warning("⚠️ Please paste some messages first.")
            else:
                with st.spinner(f"AI ({MODEL_PROVIDER}) is analyzing your transactions..."):
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
                            m_col1.metric(label="Total Tracked Amount", value=f"KES {total:,.2f}")
                            
                            csv_data = current_df.to_csv(index=False).encode('utf-8')
                            m_col2.download_button(
                                label="📥 Download CSV",
                                data=csv_data,
                                file_name="mpesa_daily_ledger.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        
                    except Exception as e:
                        st.error(f"Processing Error: {e}")
        else:
            # Render from session state / database history
            if "ledger_df" in st.session_state and not st.session_state["ledger_df"].empty:
                df = st.session_state["ledger_df"]
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                if "Amount" in df.columns:
                    total = pd.to_numeric(df["Amount"], errors="coerce").sum()
                    m_col1, m_col2 = st.columns(2)
                    m_col1.metric(label="Total Tracked Amount", value=f"KES {total:,.2f}")
                    
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    m_col2.download_button(
                        label="📥 Download CSV",
                        data=csv_data,
                        file_name="mpesa_daily_ledger.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            else:
                st.info("Awaiting input. Paste your messages on the left and click Process.")

with tab_analytics:
    st.title("📈 Business Insights & Analytics")
    st.markdown("Visual breakdown of your transaction categories and totals.")
    st.divider()

    # Check if ledger data exists in session state / database
    if "ledger_df" in st.session_state and not st.session_state["ledger_df"].empty:
        analytics_df = st.session_state["ledger_df"].copy()
        
        # Ensure Amount is treated numerically for aggregations
        analytics_df["Amount"] = pd.to_numeric(analytics_df["Amount"], errors="coerce")

        col_metric1, col_metric2 = st.columns(2)
        with col_metric1:
            total_sum = analytics_df["Amount"].sum()
            st.metric(label="Overall Amount", value=f"KES {total_sum:,.2f}")
        with col_metric2:
            total_count = len(analytics_df)
            st.metric(label="Total Transactions Processed", value=total_count)

        st.markdown("### 📊 Totals by Category")
        
        if "Category" in analytics_df.columns and "Amount" in analytics_df.columns:
            # Group data by category and sum the amounts
            category_group = analytics_df.groupby("Category")["Amount"].sum()
            
            # Render a native Streamlit bar chart
            st.bar_chart(category_group)
        else:
            st.warning("Required columns ('Category' and 'Amount') not found in dataset for charts.")
            
    else:
        st.info("ℹ️ No transaction data found yet. Please process receipts in the **Data Entry & Ledger** tab to generate analytics.")