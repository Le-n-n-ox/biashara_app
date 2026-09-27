import streamlit as st
import pandas as pd
from localization.translations import tr

def render_financial_metrics(df: pd.DataFrame):
    """Calculates and renders the top-level income and expense metrics."""
    income = df.loc[df["Type"] == "Income", "Amount (KES)"].sum() if not df.empty else 0.0
    expenses = df.loc[df["Type"] == "Expense", "Amount (KES)"].sum() if not df.empty else 0.0
    net_cash_flow = income - expenses

    st.subheader(tr("financial_overview"), anchor=False)
    st.caption(tr("transactions_tracked").format(count=f"{len(df):,}"))
    metric_income, metric_expenses, metric_net = st.columns(3, gap="medium")
    metric_income.metric(tr("total_received"), f"KES {income:,.2f}")
    metric_expenses.metric(tr("total_spent"), f"KES {expenses:,.2f}")
    metric_net.metric(tr("net_cash_flow"), f"KES {net_cash_flow:,.2f}", delta=f"{net_cash_flow:,.2f}")
    st.divider()