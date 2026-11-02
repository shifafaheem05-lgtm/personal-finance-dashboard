"""Fictional demo data so the dashboard is not empty on first run."""
from __future__ import annotations

import random
from datetime import date, timedelta

from .db import TransactionStore


def load_demo(store: TransactionStore, months: int = 3) -> int:
    rnd = random.Random(42)
    today = date.today()
    count = 0
    for m in range(months):
        total = today.year * 12 + (today.month - 1) - m
        first = date(total // 12, total % 12 + 1, 1)
        store.add(first, "income", "Salary", 85000, "Monthly salary"); count += 1
        if m % 2 == 0:
            store.add(first + timedelta(days=9), "income", "Freelance", rnd.randint(8000, 20000), "Side project"); count += 1
        store.add(first + timedelta(days=1), "expense", "Rent", 25000, "House rent"); count += 1
        store.add(first + timedelta(days=4), "expense", "Utilities", rnd.randint(4000, 7000), "Electricity and internet"); count += 1
        for d in range(2, 27, 3):
            day = first + timedelta(days=d)
            store.add(day, "expense", "Food", rnd.randint(500, 2500), "Groceries / meals"); count += 1
            if d % 2 == 0:
                store.add(day, "expense", "Transport", rnd.randint(200, 1200), "Fuel / ride"); count += 1
        store.add(first + timedelta(days=15), "expense", "Shopping", rnd.randint(2000, 9000), "Clothes"); count += 1
        store.add(first + timedelta(days=20), "expense", "Entertainment", rnd.randint(500, 3000), "Movie / outing"); count += 1
    store.set_budget("Food", 15000)
    store.set_budget("Transport", 5000)
    store.set_budget("Shopping", 6000)
    return count
