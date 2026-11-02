"""SQLite storage for transactions and monthly budgets."""
from __future__ import annotations

import csv
import io
import math
import sqlite3
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd

EXPENSE_CATEGORIES = ["Food", "Transport", "Rent", "Utilities", "Shopping",
                      "Health", "Education", "Entertainment", "Other"]
INCOME_CATEGORIES = ["Salary", "Freelance", "Gift", "Investment", "Other"]
CATEGORIES = {"expense": EXPENSE_CATEGORIES, "income": INCOME_CATEGORIES}
TYPES = ("income", "expense")
COLUMNS = ["id", "date", "type", "category", "amount", "description"]


def _parse_date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from None


class TransactionStore:
    """Small repository around a SQLite file (use ':memory:' for tests)."""

    def __init__(self, path: str = "finance.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)  # Streamlit reruns on worker threads
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS transactions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   date TEXT NOT NULL,
                   type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                   category TEXT NOT NULL,
                   amount REAL NOT NULL CHECK (amount > 0),
                   description TEXT NOT NULL DEFAULT ''
               )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS budgets (
                   category TEXT PRIMARY KEY,
                   monthly_limit REAL NOT NULL CHECK (monthly_limit > 0)
               )"""
        )
        self._conn.commit()

    # ---- transactions -------------------------------------------------
    def add(self, date_, type_: str, category: str, amount, description: str = "") -> int:
        type_ = str(type_).strip().lower()
        if type_ not in TYPES:
            raise ValueError("type must be 'income' or 'expense'")
        category = str(category).strip()
        if not category:
            raise ValueError("category is required")
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError):
            raise ValueError("amount must be a number") from None
        if not math.isfinite(amount):
            raise ValueError("amount must be a finite number")
        if amount <= 0:
            raise ValueError("amount must be greater than zero")

        cur = self._conn.execute(
            "INSERT INTO transactions (date, type, category, amount, description) VALUES (?,?,?,?,?)",
            (_parse_date(date_), type_, category, amount, str(description).strip()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def delete(self, transaction_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))
        self._conn.commit()
        return cur.rowcount > 0

    def all(self) -> pd.DataFrame:
        rows = self._conn.execute(
            "SELECT id, date, type, category, amount, description FROM transactions ORDER BY date DESC, id DESC"
        ).fetchall()
        df = pd.DataFrame([dict(r) for r in rows], columns=COLUMNS)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def clear(self) -> None:
        self._conn.execute("DELETE FROM transactions")
        self._conn.commit()

    # ---- budgets ------------------------------------------------------
    def set_budget(self, category: str, monthly_limit) -> None:
        limit = float(monthly_limit)
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("budget must be greater than zero")
        self._conn.execute(
            "INSERT INTO budgets (category, monthly_limit) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
            (category, round(limit, 2)),
        )
        self._conn.commit()

    def remove_budget(self, category: str) -> None:
        self._conn.execute("DELETE FROM budgets WHERE category = ?", (category,))
        self._conn.commit()

    def budgets(self) -> Dict[str, float]:
        return {r["category"]: r["monthly_limit"] for r in self._conn.execute("SELECT * FROM budgets")}

    # ---- CSV import / export -----------------------------------------
    def export_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["date", "type", "category", "amount", "description"])
        for r in self.all().itertuples():
            writer.writerow([r.date.date().isoformat(), r.type, r.category, r.amount, r.description])
        return buf.getvalue()

    def import_csv(self, text: str) -> Dict[str, object]:
        """Import rows; bad rows are skipped and reported, good rows are kept."""
        reader = csv.DictReader(io.StringIO(text))
        required = {"date", "type", "category", "amount"}
        if not reader.fieldnames or not required.issubset({f.strip().lower() for f in reader.fieldnames}):
            raise ValueError("CSV must have columns: date, type, category, amount (description optional)")

        imported, errors = 0, []
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): v for k, v in row.items()}
            try:
                self.add(row["date"], row["type"], row["category"], row["amount"], row.get("description") or "")
                imported += 1
            except ValueError as exc:
                errors.append(f"line {line_no}: {exc}")
        return {"imported": imported, "errors": errors}

    def close(self) -> None:
        self._conn.close()
