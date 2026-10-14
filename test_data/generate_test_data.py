"""Generate the synthetic CSV test data used by the legacy scripts.

Data is synthetic (no client data) and generated with a fixed seed per script,
so the same files are produced on every machine and changing one script's
data never changes another's. Each script gets its own folder:
test_data/<script_name>/<input files>.csv

Run: python test_data/generate_test_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def save(df: pd.DataFrame, script: str, filename: str) -> None:
    folder = ROOT / script
    folder.mkdir(exist_ok=True)
    df.to_csv(folder / filename, index=False, na_rep="NA")
    print(f"{script}/{filename}: {len(df)} rows")


def sales_monthly_summary() -> None:
    """Clean sales transactions, no trap: control case for the pipeline."""
    rng = np.random.default_rng(1)  # one generator per script: independent data
    n = 60
    dates = pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 90, n), unit="D")
    df = pd.DataFrame({
        "order_id": range(1001, 1001 + n),
        "order_date": dates.strftime("%Y-%m-%d"),
        "region": rng.choice(["North", "South", "East", "West"], n),
        "product": rng.choice(["A", "B", "C"], n),
        "units": rng.integers(1, 20, n),
        "unit_price": rng.choice([9.99, 14.50, 24.00], n),
    })
    save(df, "01_sales_monthly_summary", "sales.csv")


def hr_salary_stats() -> None:
    """Small departments (5-7 people) and two missing bonuses.

    Traps: sd() is n-1 (numpy default is n), and mean() returns NA when a
    value is missing (pandas skips NaN by default).
    """
    rng = np.random.default_rng(2)
    departments = ["Engineering", "Finance", "Marketing", "Operations", "Sales"]
    dept = np.repeat(departments, [7, 5, 6, 5, 7])
    n = len(dept)
    base = {"Engineering": 85000, "Finance": 72000, "Marketing": 61000,
            "Operations": 55000, "Sales": 58000}
    salary = np.array([base[d] for d in dept]) + rng.integers(-12000, 12000, n)
    bonus = (salary * rng.uniform(0.03, 0.12, n)).round(0)
    df = pd.DataFrame({
        "employee_id": [f"E{100 + i}" for i in range(n)],
        "department": dept,
        "job_level": rng.choice(["Junior", "Mid", "Senior"], n),
        "salary": salary,
        "bonus": bonus,
    })
    # One missing bonus in Marketing and one in Sales (e.g. new hires)
    df.loc[[13, 25], "bonus"] = np.nan
    save(df, "02_hr_salary_stats", "employees.csv")


def ops_inventory_cleaning() -> None:
    """Messy warehouse extract: inconsistent text, duplicates, non-numeric
    quantities ("N/A", "unknown"), negative counts and missing costs.

    No silent trap here, but a naive astype(float) on quantity crashes:
    this script is expected to exercise the repair loop.
    """
    rng = np.random.default_rng(3)
    n = 40
    warehouses = ["Montreal", " montreal", "MONTREAL ", "Toronto", "toronto ", "Vancouver"]
    df = pd.DataFrame({
        "sku": [f"SKU-{i:03d}" for i in rng.integers(1, 30, n)],
        "warehouse": rng.choice(warehouses, n),
        "item_name": rng.choice(["Pallet jack", " Shelf unit", "Forklift battery ", "Bin"], n),
        "quantity": rng.integers(-5, 200, n).astype(str),
        "unit_cost": rng.choice([12.5, 48.0, 310.0, 7.25], n),
        "last_count_date": (pd.to_datetime("2024-03-01")
                            + pd.to_timedelta(rng.integers(0, 120, n), unit="D")).strftime("%Y-%m-%d"),
    })
    df.loc[[4, 17], "quantity"] = "N/A"
    df.loc[29, "quantity"] = "unknown"
    df.loc[[8, 22], "unit_cost"] = np.nan
    df = pd.concat([df, df.iloc[[2, 11, 30]]], ignore_index=True)  # exact duplicates
    save(df, "03_ops_inventory_cleaning", "inventory.csv")


def sales_commission_payout() -> None:
    """Two inputs (reps + transactions) joined on rep_id.

    Trap: the script ranks reps with 1:nrow() and pays an accelerator to
    rows [1:3]. A literal port with 0-based indexing shifts ranks and pays
    the wrong reps. Rep R08 has no transaction (tests the join type).
    """
    rng = np.random.default_rng(4)
    reps = pd.DataFrame({
        "rep_id": [f"R{i:02d}" for i in range(1, 9)],
        "rep_name": ["Alice Martin", "Bilal Haddad", "Chloe Tremblay", "David Nguyen",
                     "Emma Roy", "Farid Benali", "Grace Lee", "Hugo Gagnon"],
        "team": ["East", "East", "West", "West", "East", "West", "East", "West"],
        "commission_rate": [0.05, 0.04, 0.05, 0.06, 0.04, 0.05, 0.06, 0.05],
    })
    n = 80
    txns = pd.DataFrame({
        "txn_id": [f"T{5000 + i}" for i in range(n)],
        "rep_id": rng.choice(reps.rep_id[:7], n),   # R08 never appears
        "txn_date": (pd.to_datetime("2024-01-01")
                     + pd.to_timedelta(rng.integers(0, 91, n), unit="D")).strftime("%Y-%m-%d"),
        "amount": rng.uniform(500, 15000, n).round(2),
        "status": rng.choice(["closed", "closed", "closed", "pending", "cancelled"], n),
    })
    save(reps, "04_sales_commission_payout", "sales_reps.csv")
    save(txns, "04_sales_commission_payout", "transactions.csv")


if __name__ == "__main__":
    sales_monthly_summary()
    hr_salary_stats()
    ops_inventory_cleaning()
    sales_commission_payout()
