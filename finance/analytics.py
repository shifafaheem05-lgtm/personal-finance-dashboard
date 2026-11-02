"""Pure pandas functions that turn raw transactions into dashboard numbers."""
from __future__ import annotations

from typing import Dict, List

import pandas as pd


def available_months(df: pd.DataFrame) -> List[str]:
    """Months that have data, newest first, as 'YYYY-MM'."""
    if df.empty:
        return []
    return sorted(df["date"].dt.strftime("%Y-%m").unique(), reverse=True)


def for_month(df: pd.DataFrame, month: str) -> pd.DataFrame:
    return df[df["date"].dt.strftime("%Y-%m") == month]


def monthly_summary(df: pd.DataFrame, month: str) -> Dict[str, float]:
    m = for_month(df, month)
    income = float(m.loc[m["type"] == "income", "amount"].sum())
    expenses = float(m.loc[m["type"] == "expense", "amount"].sum())
    savings = income - expenses
    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "savings": round(savings, 2),
        "savings_rate": round(savings / income * 100, 1) if income > 0 else 0.0,
    }


def category_breakdown(df: pd.DataFrame, month: str) -> pd.Series:
    """Expenses per category for the month, largest first."""
    m = for_month(df, month)
    m = m[m["type"] == "expense"]
    return m.groupby("category")["amount"].sum().sort_values(ascending=False).round(2)


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Income and expenses per month (index = 'YYYY-MM')."""
    if df.empty:
        return pd.DataFrame(columns=["income", "expense"])
    tmp = df.assign(month=df["date"].dt.strftime("%Y-%m"))
    out = tmp.pivot_table(index="month", columns="type", values="amount", aggfunc="sum", fill_value=0.0)
    for col in ("income", "expense"):
        if col not in out.columns:
            out[col] = 0.0
    return out[["income", "expense"]].sort_index().round(2)


def budget_status(df: pd.DataFrame, budgets: Dict[str, float], month: str) -> pd.DataFrame:
    """Spent vs limit per budgeted category."""
    spent = category_breakdown(df, month)
    rows = []
    for category, limit in sorted(budgets.items()):
        s = float(spent.get(category, 0.0))
        rows.append({
            "category": category,
            "spent": round(s, 2),
            "limit": round(float(limit), 2),
            "used_pct": round(s / limit * 100, 1),
            "over": s > limit,
        })
    return pd.DataFrame(rows, columns=["category", "spent", "limit", "used_pct", "over"])


def top_expenses(df: pd.DataFrame, month: str, n: int = 5) -> pd.DataFrame:
    m = for_month(df, month)
    m = m[m["type"] == "expense"]
    return m.sort_values("amount", ascending=False).head(n)[["date", "category", "amount", "description"]]
