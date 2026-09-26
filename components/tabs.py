import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# Brand palette (mirrors assets/styles.css tokens)
GREEN = "#1C8A5D"
GREEN_SOFT = "#8FCBAE"
TERRACOTTA = "#B3402A"
TERRACOTTA_SOFT = "#DE9683"
INK = "#16283A"
INK_SOFT = "#5B6B78"
BORDER = "#E4E1D8"

CATEGORY_PALETTE = [
    "#B3402A", "#C6603F", "#D18B6C", "#8B6F4E", "#5B6B78",
    "#7A8A97", "#A3826A", "#9C5A44", "#4E6B5C", "#C9A27A",
]


def _base_layout(height=340, showlegend=False):
    """Shared Plotly layout: transparent background so it follows the app
    theme, ink-toned text, minimal chrome."""
    return dict(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=INK, size=13),
        showlegend=showlegend,
        hoverlabel=dict(
            bgcolor="white",
            font_size=13,
            font_family="Inter, sans-serif",
            bordercolor=BORDER,
        ),
        xaxis=dict(showgrid=False, showline=True, linecolor=BORDER, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False),
    )


def render_ledger_and_analytics(df: pd.DataFrame):
    """Renders the ledger table and analytics charts in tabs."""
    ledger_tab, analytics_tab = st.tabs(["Daily Ledger", "Analytics Dashboard"])

    with ledger_tab:
        if df.empty:
            st.info("Your ledger is currently empty. Open the expander above to process your first receipts.")
        else:
            display_df = df.copy()
            display_df["Channel"] = display_df["Channel"].fillna("Unknown") if "Channel" in display_df else "Unknown"

            channel_options = sorted(display_df["Channel"].unique())
            selected_channels = st.multiselect(
                "Filter by payment channel",
                options=channel_options,
                default=channel_options,
            )
            display_df = display_df[display_df["Channel"].isin(selected_channels)]

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Export to CSV",
                data=display_df.to_csv(index=False).encode("utf-8"),
                file_name=f"biashara_ledger_{datetime.now():%Y%m%d}.csv",
                mime="text/csv",
            )

    with analytics_tab:
        if df.empty:
            st.info("No transaction data available for analytics yet.")
            return

        # ---------- Expense breakdown ----------
        expense_df = df[df["Type"] == "Expense"]
        if not expense_df.empty:
            st.markdown("#### Expense Breakdown")
            category_summary = (
                expense_df.groupby("Category")["Amount (KES)"]
                .sum()
                .sort_values(ascending=True)
            )

            chart_col, table_col = st.columns([2, 1])
            with chart_col:
                colors = (CATEGORY_PALETTE * (len(category_summary) // len(CATEGORY_PALETTE) + 1))[:len(category_summary)]
                fig = go.Figure(go.Bar(
                    x=category_summary.values,
                    y=category_summary.index,
                    orientation="h",
                    marker=dict(color=colors, line=dict(width=0)),
                    text=[f"KES {v:,.0f}" for v in category_summary.values],
                    textposition="outside",
                    textfont=dict(color=INK, size=12),
                    hovertemplate="<b>%{y}</b><br>KES %{x:,.2f}<extra></extra>",
                ))
                layout = _base_layout(height=max(260, 42 * len(category_summary)))
                layout["xaxis"]["showgrid"] = True
                layout["xaxis"]["gridcolor"] = BORDER
                layout["yaxis"]["showgrid"] = False
                fig.update_layout(**layout)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            with table_col:
                st.dataframe(
                    category_summary.sort_values(ascending=False).rename("Amount (KES)"),
                    use_container_width=True,
                )
        else:
            st.info("No expenses recorded yet.")

        st.divider()

        # ---------- Cash flow comparison ----------
        st.markdown("#### Cash Flow Comparison")
        cash_flow = df.groupby("Type")["Amount (KES)"].sum()
        income_val = cash_flow.get("Income", 0)
        expense_val = cash_flow.get("Expense", 0)

        fig = go.Figure(go.Bar(
            x=["Income", "Expense"],
            y=[income_val, expense_val],
            marker=dict(color=[GREEN, TERRACOTTA], line=dict(width=0)),
            width=0.5,
            text=[f"KES {income_val:,.0f}", f"KES {expense_val:,.0f}"],
            textposition="outside",
            textfont=dict(color=INK, size=13),
            hovertemplate="<b>%{x}</b><br>KES %{y:,.2f}<extra></extra>",
        ))
        layout = _base_layout(height=300)
        layout["xaxis"]["showgrid"] = False
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        net = income_val - expense_val
        net_color = GREEN if net >= 0 else TERRACOTTA
        st.markdown(
            f"<p style='color:{net_color}; font-weight:600; margin-top:-10px;'>"
            f"Net position: KES {net:,.2f}</p>",
            unsafe_allow_html=True,
        )

        st.divider()

        # ---------- Payment channel breakdown ----------
        st.markdown("#### Payment Channel Breakdown")
        st.caption("How money moved: Send Money, Paybill, Till (Buy Goods), or Received.")

        channel_df = df.copy()
        channel_df["Channel"] = channel_df["Channel"].fillna("Unknown") if "Channel" in channel_df else "Unknown"
        channel_summary = (
            channel_df.groupby("Channel")["Amount (KES)"]
            .sum()
            .sort_values(ascending=True)
        )

        channel_chart_col, channel_table_col = st.columns([2, 1])
        with channel_chart_col:
            fig = go.Figure(go.Bar(
                x=channel_summary.values,
                y=channel_summary.index,
                orientation="h",
                marker=dict(
                    color=INK_SOFT,
                    line=dict(width=0),
                ),
                text=[f"KES {v:,.0f}" for v in channel_summary.values],
                textposition="outside",
                textfont=dict(color=INK, size=12),
                hovertemplate="<b>%{y}</b><br>KES %{x:,.2f}<extra></extra>",
            ))
            layout = _base_layout(height=max(220, 50 * len(channel_summary)))
            layout["yaxis"]["showgrid"] = False
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with channel_table_col:
            st.dataframe(
                channel_summary.sort_values(ascending=False).rename("Amount (KES)"),
                use_container_width=True,
            )