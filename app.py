import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from database import (
    clear_db,
    get_entity_memory,
    init_db,
    load_transactions_from_db,
    save_transactions_to_db,
    update_entity_memory,
)
from utils.ai_router import process_sms_with_ai
from utils.fraud_detector import analyze_mpesa_fraud

load_dotenv()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").strip().upper()
AI_PROVIDERS = {
    "Ollama": "OLLAMA",
    "Google Gemini": "GEMINI",
    "NVIDIA Brev API": "NVIDIA",
}
DEFAULT_PROVIDER_LABEL = next(
    (label for label, provider in AI_PROVIDERS.items() if provider == MODEL_PROVIDER),
    "Ollama",
)

init_db()
st.set_page_config(
    page_title="Biashara Bookkeeper",
    page_icon="📒",
    layout="wide",
    initial_sidebar_state="expanded",
)


def process_receipt_pipeline(raw_text: str) -> list[dict]:
    """Parse M-Pesa receipt lines into the ledger schema for local/webhook use."""
    parsed_data = []

    for line in raw_text.splitlines():
        line = line.strip()
        txn_match = re.search(r"^([A-Z0-9]{8,12})\b", line)
        if not txn_match:
            continue
        if analyze_mpesa_fraud(line)["is_suspicious"]:
            continue

        date_match = re.search(r"\bon (\d{1,2}/\d{1,2}/\d{2})\b", line)
        if date_match:
            try:
                transaction_date = datetime.strptime(date_match.group(1), "%d/%m/%y").strftime("%Y-%m-%d")
            except ValueError:
                transaction_date = date_match.group(1)
        else:
            transaction_date = datetime.now().strftime("%Y-%m-%d")

        lower_line = line.lower()
        if "received ksh" in lower_line:
            txn_type = "Income"
            amount_match = re.search(r"received\s+Ksh\s?([\d,]+\.\d{2})", line, re.IGNORECASE)
            entity_match = re.search(r"from (.*?)\s+\d{10}\s+on", line, re.IGNORECASE)
            if not entity_match:
                entity_match = re.search(r"from (.*?) on", line, re.IGNORECASE)
        elif "sent to" in lower_line:
            txn_type = "Expense"
            amount_match = re.search(r"Ksh\s?([\d,]+\.\d{2}) sent to", line, re.IGNORECASE)
            entity_match = re.search(r"sent to (.*?)(?: for account\b| on\b)", line, re.IGNORECASE)
        elif "paid to" in lower_line:
            txn_type = "Expense"
            amount_match = re.search(r"Ksh\s?([\d,]+\.\d{2}) paid to", line, re.IGNORECASE)
            entity_match = re.search(r"paid to (.*?) on", line, re.IGNORECASE)
        else:
            continue

        if not amount_match:
            continue
        amount = float(amount_match.group(1).replace(",", ""))
        entity = entity_match.group(1).strip() if entity_match else "UNKNOWN"
        entity_upper = entity.upper()

        if any(name in entity_upper for name in ("SUPERMARKET", "CARREFOUR", "ZUCCHINI", "CHANDARANA", "FOODPLUS", "WHOLESALER")):
            category = "Inventory / Supplies"
        elif any(name in entity_upper for name in ("KPLC", "POWER")):
            category = "Utilities"
        elif any(name in entity_upper for name in ("JAVA", "SHELL", "UBER")):
            category = "Operating Expenses"
        elif txn_type == "Income":
            category = "Sales / Income"
        else:
            category = "Transfer / Payroll"

        parsed_data.append({
            "Transaction Code": txn_match.group(1),
            "Date": transaction_date,
            "Entity": entity,
            "Type": txn_type,
            "Amount (KES)": amount,
            "Category": category,
        })

    return parsed_data


def process_with_ai(raw_text: str, provider: str) -> list[dict]:
    """Use AI categories where available, while keeping the local parser's ledger fields."""
    parsed_data = process_receipt_pipeline(raw_text)
    ai_data = process_sms_with_ai(raw_text, provider)

    if not parsed_data:
        codes = re.findall(r"^([A-Z0-9]{8,12})\b", raw_text, re.MULTILINE)
        lines = raw_text.splitlines()
        parsed_data = []
        for index, item in enumerate(ai_data):
            if index >= len(codes):
                continue
            line = lines[index] if index < len(lines) else ""
            amount = item.get("Amount (KES)", item.get("Amount", 0))
            try:
                amount = float(str(amount).replace(",", ""))
            except (TypeError, ValueError):
                continue
            parsed_data.append({
                "Transaction Code": item.get("Transaction Code", codes[index]),
                "Date": item.get("Date", datetime.now().strftime("%Y-%m-%d")),
                "Entity": item.get("Entity", "UNKNOWN"),
                "Type": item.get("Type", "Income" if "received" in line.lower() else "Expense"),
                "Amount (KES)": amount,
                "Category": item.get("Category", "Unknown"),
            })
    else:
        for index, item in enumerate(ai_data):
            if index < len(parsed_data) and item.get("Category"):
                parsed_data[index]["Category"] = item["Category"]

    memory = get_entity_memory()
    for transaction in parsed_data:
        entity = transaction["Entity"].strip().upper()
        if entity in memory:
            transaction["Category"] = memory[entity]
        elif entity and transaction.get("Category"):
            update_entity_memory(entity, transaction["Category"])

    return parsed_data


with st.sidebar:
    st.header("⚙️ Settings")
    selected_label = st.selectbox(
        "Active AI Model",
        list(AI_PROVIDERS),
        index=list(AI_PROVIDERS).index(DEFAULT_PROVIDER_LABEL),
    )
    selected_provider = AI_PROVIDERS[selected_label]
    st.caption("The local receipt parser is used if the selected AI provider is unavailable.")

    st.markdown("---")
    st.markdown("### 🧠 AI Memory Cache")
    memory_cache = get_entity_memory()
    if memory_cache:
        for entity, category in list(memory_cache.items())[:5]:
            st.caption(f"{entity} → {category}")
        if len(memory_cache) > 5:
            st.caption(f"...and {len(memory_cache) - 5} more")
    else:
        st.caption("No entities learned yet.")

    if st.button("🗑️ Clear Database", type="secondary", use_container_width=True):
        clear_db()
        st.rerun()

st.title("Biashara Bookkeeper 📒")
st.markdown("Paste raw M-Pesa SMS receipts to update your business ledger.")
raw_sms = st.text_area(
    "M-Pesa SMS Input (batch parsing supported)",
    height=180,
    placeholder="Paste contents of sample_mpesa.txt here...",
)

if st.button("Process Receipts", type="primary"):
    if not raw_sms.strip():
        st.warning("Please paste at least one SMS receipt first.")
    else:
        receipt_lines = [
            line for line in raw_sms.splitlines()
            if re.match(r"^[A-Z0-9]{8,12}\b", line.strip())
        ]
        checks = [analyze_mpesa_fraud(line) for line in receipt_lines]
        safe_lines = [line for line, check in zip(receipt_lines, checks) if not check["is_suspicious"]]
        blocked_checks = [check for check in checks if check["is_suspicious"]]

        if blocked_checks:
            st.error(blocked_checks[0]["reason"])
            st.warning(f"Blocked {len(blocked_checks)} suspicious receipt(s).")

        if not safe_lines:
            st.info("No safe receipts were available to add to the ledger.")
        else:
            safe_sms = "\n".join(safe_lines)
            try:
                with st.spinner(f"Processing with {selected_label}..."):
                    transactions = process_with_ai(safe_sms, selected_provider)
            except Exception as error:
                transactions = process_receipt_pipeline(safe_sms)
                st.warning(f"AI processing failed; used the local parser instead. Details: {error}")

            new_df = pd.DataFrame(transactions)
            existing_df = load_transactions_from_db()
            if not new_df.empty:
                if not existing_df.empty:
                    new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]
                new_df = new_df.drop_duplicates(subset=["Transaction Code"])
                if not new_df.empty:
                    save_transactions_to_db(new_df)
                    st.success(f"Saved {len(new_df)} new receipt(s).")
                    st.rerun()

            if new_df.empty:
                st.info("No new receipts found; they may already be in your ledger or use an unsupported format.")

st.divider()
st.subheader("Financial Overview")
df = load_transactions_from_db()

income = df.loc[df["Type"] == "Income", "Amount (KES)"].sum() if not df.empty else 0.0
expenses = df.loc[df["Type"] == "Expense", "Amount (KES)"].sum() if not df.empty else 0.0
net_cash_flow = income - expenses
metric_income, metric_expenses, metric_net = st.columns(3)
metric_income.metric("Total Received", f"KES {income:,.2f}")
metric_expenses.metric("Total Spent", f"KES {expenses:,.2f}")
metric_net.metric("Net Cash Flow", f"KES {net_cash_flow:,.2f}", delta=f"{net_cash_flow:,.2f}")

ledger_tab, analytics_tab = st.tabs(["🧾 Daily Ledger", "📊 Analytics Dashboard"])
with ledger_tab:
    if df.empty:
        st.info("Your ledger is currently empty. Process receipts above to populate it.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Download Ledger as CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"biashara_ledger_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
        )

with analytics_tab:
    if df.empty:
        st.info("No transactions are available for analytics yet.")
    else:
        expense_df = df[df["Type"] == "Expense"]
        if not expense_df.empty:
            st.markdown("### Expense Breakdown")
            category_summary = expense_df.groupby("Category")["Amount (KES)"].sum().sort_values(ascending=False)
            chart_column, table_column = st.columns(2)
            chart_column.bar_chart(category_summary)
            table_column.dataframe(category_summary.rename("Amount (KES)"), use_container_width=True)
        else:
            st.info("No expenses recorded yet.")

        st.markdown("### Cash Flow Comparison")
        cash_flow = df.groupby("Type")["Amount (KES)"].sum()
        st.bar_chart(cash_flow)
