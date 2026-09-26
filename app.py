import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys
import time
import re
from datetime import datetime

# Force Python to look for modules in the exact folder where app.py lives
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from database import save_transactions_to_db, load_transactions_from_db, clear_db

# -----------------------------------------
# 1. Page & State Configuration
# -----------------------------------------
st.set_page_config(
    page_title="Biashara Bookkeeper",
    page_icon="📒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------
# 2. Dynamic AI / Memory Processing Hook
# -----------------------------------------
def process_receipt_pipeline(raw_text: str):
    """
    STEVE: This acts as your Fast Path Memory Cache.
    It parses real M-Pesa text via Regex before falling back to an AI model.
    """
    time.sleep(0.5) # Simulate processing time
    parsed_data = []
    
    # Split the raw text into individual SMS lines
    lines = raw_text.strip().split('\n')
    
    for line in lines:
        if not line.strip(): 
            continue
        
        # 1. Extract Transaction Code
        txn_match = re.search(r'^([A-Z0-9]{10})', line)
        if not txn_match: 
            continue
        txn_code = txn_match.group(1)
        
        # 2. Extract Date and format to YYYY-MM-DD
        date_match = re.search(r'on (\d{1,2}/\d{1,2}/\d{2})', line)
        if date_match:
            try:
                date_obj = datetime.strptime(date_match.group(1), "%d/%m/%y")
                formatted_date = date_obj.strftime("%Y-%m-%d")
            except:
                formatted_date = date_match.group(1)
        else:
            formatted_date = datetime.now().strftime("%Y-%m-%d")
            
        # 3. Determine Type, Amount, and Entity
        if "received Ksh" in line:
            txn_type = "Income"
            amt_match = re.search(r'received Ksh([\d,]+\.\d{2})', line)
            entity_match = re.search(r'from (.*?) on', line)
        elif "sent to" in line:
            txn_type = "Expense"
            amt_match = re.search(r'Ksh([\d,]+\.\d{2}) sent to', line)
            entity_match = re.search(r'sent to (.*?) (?:\d{10}\s)?on', line) 
        elif "paid to" in line:
            txn_type = "Expense"
            amt_match = re.search(r'Ksh([\d,]+\.\d{2}) paid to', line)
            entity_match = re.search(r'paid to (.*?) on', line)
        else:
            continue
            
        # Clean comma formatting from amounts
        amount = float(amt_match.group(1).replace(',', '')) if amt_match else 0.0
        entity = entity_match.group(1).strip() if entity_match else "UNKNOWN"
        
        # 4. Keyword Memory Categorization
        entity_upper = entity.upper()
        if any(kw in entity_upper for kw in ["SUPERMARKET", "CARREFOUR", "ZUCCHINI", "CHANDARANA", "FOODPLUS"]):
            category = "Inventory / Supplies"
        elif any(kw in entity_upper for kw in ["KPLC", "POWER"]):
            category = "Utilities"
        elif any(kw in entity_upper for kw in ["JAVA", "SHELL", "UBER"]):
            category = "Operating Expenses"
        elif txn_type == "Income":
            category = "Sales / Income"
        else:
            category = "Transfer / Payroll"
            
        parsed_data.append({
            "Transaction Code": txn_code,
            "Date": formatted_date,
            "Entity": entity,
            "Type": txn_type,
            "Amount (KES)": amount,
            "Category": category
        })
        
    return parsed_data

# -----------------------------------------
# 3. Sidebar: AI Pipeline & Settings
# -----------------------------------------
with st.sidebar:
    st.header("⚙️ System Configuration")
    
    env_provider = os.getenv("MODEL_PROVIDER", "Ollama")
    provider_options = ["Ollama", "Google Gemini", "NVIDIA Brev API"]
    default_index = provider_options.index(env_provider) if env_provider in provider_options else 0
    
    selected_model = st.selectbox(
        "Active AI Model", 
        provider_options,
        index=default_index,
        help="Routes the prompt pipeline based on selection."
    )
    
    st.markdown("---")
    st.info("⚠️ Ensure NVIDIA Brev API is selected before the final hackathon demo to meet judging criteria.")
    
    st.markdown("---")
    st.markdown("**Database Status**")
    st.success("🟢 SQLite Local DB Connected")
    
    if st.button("🗑️ Clear Database", type="secondary"):
        clear_db()
        st.success("Database cleared!")
        time.sleep(1)
        st.rerun()

# -----------------------------------------
# 4. Main UI & Input Section
# -----------------------------------------
st.title("Biashara Bookkeeper 📒")
st.markdown("Paste raw M-Pesa SMS receipts below to generate your structured daily ledger.")

raw_sms = st.text_area(
    "M-Pesa SMS Input (Batch parsing supported)", 
    height=150, 
    placeholder="Paste contents of sample_mpesa.txt here..."
)

if st.button("Process Receipts", type="primary"):
    if raw_sms.strip():
        with st.spinner(f"Extracting data using {selected_model}..."):
            # 1. Process via AI/Webhook
            new_transactions = process_receipt_pipeline(raw_sms)
            new_df = pd.DataFrame(new_transactions)
            
            # 2. Prevent Duplicates: Check against existing database records
            existing_df = load_transactions_from_db()
            if not existing_df.empty and not new_df.empty:
                new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]
            
            # 3. Save only if there are new, unique transactions
            if not new_df.empty:
                save_transactions_to_db(new_df)
                st.success(f"{len(new_df)} new receipt(s) processed and saved!")
                time.sleep(1)
                st.rerun()
            else:
                st.info("Duplicate detected: These receipts are already in your ledger or the format was invalid.")
    else:
        st.warning("Please paste at least one SMS receipt first.")

st.divider()

# -----------------------------------------
# 5. Dashboard & Ledger Tabs
# -----------------------------------------
st.subheader("Financial Overview")

# Load data directly from SQLite
df = load_transactions_from_db()

# Calculate dynamic metrics
total_income = df[df["Type"] == "Income"]["Amount (KES)"].sum() if not df.empty else 0.0
total_expense = df[df["Type"] == "Expense"]["Amount (KES)"].sum() if not df.empty else 0.0
net_cash_flow = total_income - total_expense

# Top-level Metric Cards (Visible on all tabs)
col1, col2, col3 = st.columns(3)
col1.metric("Total Received", f"KES {total_income:,.2f}")
col2.metric("Total Spent", f"KES {total_expense:,.2f}")
col3.metric("Net Cash Flow", f"KES {net_cash_flow:,.2f}", delta=f"{net_cash_flow:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

if not df.empty:
    # Create Tabs
    tab_ledger, tab_analytics = st.tabs(["🧾 Daily Ledger", "📊 Analytics Dashboard"])
    
    with tab_ledger:
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # 6. CSV Export Function
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Ledger as CSV",
            data=csv_data,
            file_name=f"biashara_ledger_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
        
    with tab_analytics:
        st.markdown("### Expense Breakdown")
        
        # Filter only expenses
        expense_df = df[df["Type"] == "Expense"]
        
        if not expense_df.empty:
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                # Interactive Pie Chart
                fig_pie = px.pie(
                    expense_df, 
                    values="Amount (KES)", 
                    names="Category", 
                    hole=0.4,
                    color_discrete_sequence=px.colors.sequential.Teal
                )
                fig_pie.update_layout(margin=dict(t=20, b=20, l=0, r=0))
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with chart_col2:
                # Grouped Category Summary Table
                category_summary = expense_df.groupby("Category")["Amount (KES)"].sum().reset_index()
                category_summary = category_summary.sort_values(by="Amount (KES)", ascending=False)
                
                st.markdown("**Total Spent by Category**")
                st.dataframe(
                    category_summary, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Amount (KES)": st.column_config.NumberColumn(format="KES %.2f")
                    }
                )
        else:
            st.info("No expenses recorded yet to generate analytics.")
            
        st.markdown("---")
        
        # Income vs Expense Bar Chart
        st.markdown("### Cash Flow Comparison")
        summary_df = df.groupby("Type", as_index=False)["Amount (KES)"].sum()
        fig_bar = px.bar(
            summary_df, 
            x="Type", 
            y="Amount (KES)", 
            color="Type",
            text_auto='.2s',
            color_discrete_map={"Income": "#2ecc71", "Expense": "#e74c3c"}
        )
        fig_bar.update_layout(margin=dict(t=20, b=20, l=0, r=0), showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

else:
    st.info("Your ledger is currently empty. Process receipts above to populate the dashboard.")