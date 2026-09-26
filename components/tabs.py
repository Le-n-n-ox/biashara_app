import streamlit as st
import pandas as pd
from datetime import datetime

def render_ledger_and_analytics(df: pd.DataFrame):
    """Renders the ledger table and analytics charts in tabs."""
    ledger_tab, analytics_tab = st.tabs(["🧾 Daily Ledger", "📊 Analytics Dashboard"])

    with ledger_tab:
        if df.empty:
            st.info("📭 Your ledger is currently empty. Open the expander above to process your first receipts.")
        else:
            display_df = df.copy()
            display_df["Type"] = display_df["Type"].map({"Income": "🟢 Income", "Expense": "🔴 Expense"})
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Export to CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"biashara_ledger_{datetime.now():%Y%m%d}.csv",
                mime="text/csv",
            )

    with analytics_tab:
        if df.empty:
            st.info("📭 No transaction data available for analytics yet.")
        else:
            expense_df = df[df["Type"] == "Expense"]
            if not expense_df.empty:
                st.markdown("### Expense Breakdown")
                category_summary = expense_df.groupby("Category")["Amount (KES)"].sum().sort_values(ascending=False)
                chart_column, table_column = st.columns(2)
                
                with chart_column:
                    st.bar_chart(category_summary)
                with table_column:
                    st.dataframe(category_summary.rename("Amount (KES)"), use_container_width=True)
            else:
                st.info("No expenses recorded yet.")

            st.markdown("### Cash Flow Comparison")
            cash_flow = df.groupby("Type")["Amount (KES)"].sum()
            st.bar_chart(cash_flow)