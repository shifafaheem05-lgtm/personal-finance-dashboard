"""Personal Finance Dashboard - Streamlit app.  Run: streamlit run app.py"""
import os
from datetime import date

import pandas as pd
import streamlit as st

from finance import CATEGORIES, TransactionStore, analytics
from finance.demo import load_demo

st.set_page_config(page_title="Personal Finance Dashboard", page_icon="💰", layout="wide")


@st.cache_resource
def _shared_store() -> TransactionStore:
    return TransactionStore(os.environ.get("FINANCE_DB", "finance.db"))


def get_store() -> TransactionStore:
    """Local use: one persistent finance.db.
    Hosted demo (DEMO_MODE=1): a private in-memory database per visitor, pre-filled with demo data."""
    if os.environ.get("DEMO_MODE") == "1":
        if "store" not in st.session_state:
            st.session_state["store"] = TransactionStore(":memory:")
            load_demo(st.session_state["store"])
        return st.session_state["store"]
    return _shared_store()


store = get_store()

st.title("💰 Personal Finance Dashboard")

# ---------------- Sidebar: add data ----------------
with st.sidebar:
    st.header("Add transaction")
    with st.form("add_tx", clear_on_submit=True):
        tx_type = st.radio("Type", ["expense", "income"], horizontal=True)
        tx_date = st.date_input("Date", value=date.today())
        tx_cat = st.selectbox("Category", CATEGORIES[tx_type])
        tx_amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f")
        tx_desc = st.text_input("Description (optional)")
        if st.form_submit_button("Add"):
            try:
                store.add(tx_date, tx_type, tx_cat, tx_amount, tx_desc)
                st.success("Transaction added.")
            except ValueError as exc:
                st.error(str(exc))

    st.header("Budget")
    with st.form("budget"):
        b_cat = st.selectbox("Expense category", CATEGORIES["expense"])
        b_limit = st.number_input("Monthly limit", min_value=0.0, step=500.0, format="%.2f")
        if st.form_submit_button("Save budget"):
            try:
                store.set_budget(b_cat, b_limit)
                st.success("Budget saved.")
            except ValueError as exc:
                st.error(str(exc))

    st.header("Data")
    upload = st.file_uploader("Import CSV", type="csv")
    if upload is not None and st.button("Import file"):
        try:
            result = store.import_csv(upload.getvalue().decode("utf-8-sig"))
            st.success(f"Imported {result['imported']} rows.")
            for err in result["errors"][:5]:
                st.warning(err)
        except ValueError as exc:
            st.error(str(exc))
    st.download_button("Export CSV", store.export_csv(), "transactions.csv", "text/csv")
    if st.button("Load demo data"):
        load_demo(store)
        st.success("Demo data loaded.")

# ---------------- Main ----------------
df = store.all()  # read after the sidebar so adds/imports show up immediately
months = analytics.available_months(df)
if not months:
    st.info("No transactions yet. Add one from the sidebar, import a CSV, or click **Load demo data**.")
    st.stop()

month = st.selectbox("Month", months)
summary = analytics.monthly_summary(df, month)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Income", f"{summary['income']:,.0f}")
c2.metric("Expenses", f"{summary['expenses']:,.0f}")
c3.metric("Savings", f"{summary['savings']:,.0f}")
c4.metric("Savings rate", f"{summary['savings_rate']}%")

left, right = st.columns(2)
with left:
    st.subheader("Spending by category")
    breakdown = analytics.category_breakdown(df, month)
    if breakdown.empty:
        st.caption("No expenses this month.")
    else:
        st.bar_chart(breakdown)
with right:
    st.subheader("Income vs expenses by month")
    st.line_chart(analytics.monthly_trend(df))

st.subheader("Budgets")
status = analytics.budget_status(df, store.budgets(), month)
if status.empty:
    st.caption("No budgets set. Add one from the sidebar.")
for row in status.itertuples():
    label = f"{row.category}: {row.spent:,.0f} / {row.limit:,.0f}"
    if row.over:
        st.error(f"⚠️ {label} (over budget)")
    else:
        st.write(label)
    st.progress(min(row.used_pct / 100, 1.0))

st.subheader("Largest expenses")
top = analytics.top_expenses(df, month)
top["date"] = top["date"].dt.date
st.dataframe(top, hide_index=True, width="stretch")

st.subheader("All transactions")
view = df.copy()
view["date"] = view["date"].dt.date
st.dataframe(view, hide_index=True, width="stretch")
with st.expander("Delete a transaction"):
    del_id = st.number_input("Transaction id", min_value=1, step=1)
    if st.button("Delete"):
        if store.delete(int(del_id)):
            st.rerun()
        else:
            st.warning("No transaction with that id.")
