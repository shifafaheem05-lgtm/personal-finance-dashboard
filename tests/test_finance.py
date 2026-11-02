import os
import tempfile
import unittest

import pandas as pd

from finance import TransactionStore, analytics
from finance.demo import load_demo


def seeded():
    s = TransactionStore(":memory:")
    s.add("2026-01-01", "income", "Salary", 1000)
    s.add("2026-01-05", "expense", "Food", 200)
    s.add("2026-01-09", "expense", "Rent", 300)
    s.add("2026-02-01", "income", "Salary", 1000)
    s.add("2026-02-03", "expense", "Food", 50)
    return s


class StoreTests(unittest.TestCase):
    def test_add_and_list(self):
        s = seeded()
        df = s.all()
        self.assertEqual(len(df), 5)
        self.assertEqual(df.iloc[0]["date"].strftime("%Y-%m-%d"), "2026-02-03")  # newest first

    def test_validation(self):
        s = TransactionStore(":memory:")
        for args in [("2026-01-01", "loan", "X", 5), ("2026-01-01", "expense", "", 5),
                     ("2026-01-01", "expense", "Food", 0), ("2026-01-01", "expense", "Food", "abc"),
                     ("01/01/2026", "expense", "Food", 5)]:
            with self.assertRaises(ValueError, msg=str(args)):
                s.add(*args)

    def test_delete(self):
        s = seeded()
        tid = int(s.all().iloc[0]["id"])
        self.assertTrue(s.delete(tid))
        self.assertFalse(s.delete(tid))
        self.assertEqual(len(s.all()), 4)

    def test_budget_upsert(self):
        s = TransactionStore(":memory:")
        s.set_budget("Food", 100)
        s.set_budget("Food", 150)
        self.assertEqual(s.budgets(), {"Food": 150.0})
        with self.assertRaises(ValueError):
            s.set_budget("Food", 0)

    def test_csv_round_trip(self):
        s = seeded()
        text = s.export_csv()
        t = TransactionStore(":memory:")
        result = t.import_csv(text)
        self.assertEqual(result["imported"], 5)
        self.assertEqual(result["errors"], [])
        self.assertAlmostEqual(t.all()["amount"].sum(), s.all()["amount"].sum())

    def test_csv_bad_rows_are_reported_not_fatal(self):
        t = TransactionStore(":memory:")
        text = "date,type,category,amount\n2026-01-01,expense,Food,10\nnot-a-date,expense,Food,5\n2026-01-02,expense,Food,-3\n"
        result = t.import_csv(text)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(len(result["errors"]), 2)

    def test_non_finite_amounts_rejected(self):
        t = TransactionStore(":memory:")
        for bad in ("nan", "inf", "-inf"):
            with self.assertRaises(ValueError, msg=bad):
                t.add("2026-01-01", "expense", "Food", bad)
        result = t.import_csv("date,type,category,amount\n2026-01-01,expense,Food,nan\n")
        self.assertEqual((result["imported"], len(result["errors"])), (0, 1))

    def test_csv_missing_columns(self):
        with self.assertRaises(ValueError):
            TransactionStore(":memory:").import_csv("a,b\n1,2\n")


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.store = seeded()
        self.df = self.store.all()

    def test_months(self):
        self.assertEqual(analytics.available_months(self.df), ["2026-02", "2026-01"])

    def test_summary(self):
        s = analytics.monthly_summary(self.df, "2026-01")
        self.assertEqual((s["income"], s["expenses"], s["savings"], s["savings_rate"]), (1000, 500, 500, 50.0))

    def test_summary_without_income_has_zero_rate(self):
        s = TransactionStore(":memory:")
        s.add("2026-03-01", "expense", "Food", 10)
        self.assertEqual(analytics.monthly_summary(s.all(), "2026-03")["savings_rate"], 0.0)

    def test_breakdown_sorted(self):
        b = analytics.category_breakdown(self.df, "2026-01")
        self.assertEqual(list(b.index), ["Rent", "Food"])

    def test_trend(self):
        t = analytics.monthly_trend(self.df)
        self.assertEqual(list(t.index), ["2026-01", "2026-02"])
        self.assertEqual(t.loc["2026-02", "expense"], 50)

    def test_trend_empty(self):
        self.assertTrue(analytics.monthly_trend(TransactionStore(":memory:").all()).empty)

    def test_budget_status(self):
        st = analytics.budget_status(self.df, {"Food": 150, "Rent": 400}, "2026-01")
        food = st[st.category == "Food"].iloc[0]
        rent = st[st.category == "Rent"].iloc[0]
        self.assertTrue(food["over"]); self.assertEqual(food["used_pct"], 133.3)
        self.assertFalse(rent["over"])

    def test_demo_months_are_consecutive(self):
        from datetime import date
        from unittest import mock
        for today in (date(2026, 3, 1), date(2026, 3, 31), date(2026, 1, 15)):
            s = TransactionStore(":memory:")
            with mock.patch("finance.demo.date") as d:
                d.today.return_value = today
                d.side_effect = date
                load_demo(s)
            months = sorted(analytics.available_months(s.all()))
            self.assertEqual(len(months), 3, (today, months))
            idx = [int(m[:4]) * 12 + int(m[5:]) for m in months]
            self.assertEqual(idx[2] - idx[1], 1); self.assertEqual(idx[1] - idx[0], 1)

    def test_demo_data(self):
        s = TransactionStore(":memory:")
        self.assertGreater(load_demo(s), 20)
        self.assertTrue(s.budgets())


class AppSmokeTest(unittest.TestCase):
    def test_app_renders_empty_and_with_data(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            os.environ["FINANCE_DB"] = os.path.join(tmp, "t.db")
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            at = AppTest.from_file(os.path.join(root, "app.py"), default_timeout=30).run()
            self.assertFalse(at.exception, at.exception)
            self.assertTrue(any("No transactions yet" in i.value for i in at.info))

            store = TransactionStore(os.environ["FINANCE_DB"])
            load_demo(store)
            store.close()
            at = AppTest.from_file(os.path.join(root, "app.py"), default_timeout=30).run()
            self.assertFalse(at.exception, at.exception)
            self.assertGreaterEqual(len(at.metric), 4)

    def test_demo_mode_is_private_and_prefilled(self):
        from streamlit.testing.v1 import AppTest
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.environ["DEMO_MODE"] = "1"
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                os.environ["FINANCE_DB"] = os.path.join(tmp, "never_used.db")
                at = AppTest.from_file(os.path.join(root, "app.py"), default_timeout=30).run()
                self.assertFalse(at.exception, at.exception)
                self.assertGreaterEqual(len(at.metric), 4)  # demo data already loaded
                self.assertFalse(os.path.exists(os.environ["FINANCE_DB"]))  # no shared file created
                self.assertFalse(any(b.label == "Load demo data" for b in at.button))  # hidden: data is pre-loaded
        finally:
            os.environ.pop("DEMO_MODE", None)


if __name__ == "__main__":
    unittest.main()
