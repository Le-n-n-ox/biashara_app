import streamlit as st
import pandas as pd

def render_financial_metrics(df: pd.DataFrame):
    """Calculates and renders the top-level income and expense metrics."""
    income = df.loc[df["Type"] == "Income", "Amount (KES)"].sum() if not df.empty else 0.0
    expenses = df.loc[df["Type"] == "Expense", "Amount (KES)"].sum() if not df.empty else 0.0
    net_cash_flow = income - expenses

    st.subheader("Financial Overview")
    metric_income, metric_expenses, metric_net = st.columns(3)
    metric_income.metric("Total Received", f"KES {income:,.2f}")
    metric_expenses.metric("Total Spent", f"KES {expenses:,.2f}")
    metric_net.metric("Net Cash Flow", f"KES {net_cash_flow:,.2f}", delta=f"{net_cash_flow:,.2f}")
    st.divider()