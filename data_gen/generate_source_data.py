"""Generate a synthetic-but-realistic set of SaaS source extracts.

Three source systems are simulated, each with its own honest data-quality
problems — this mirrors what a real analytics-engineering pipeline actually
has to reconcile, not a pre-cleaned demo dataset:

1. **CRM daily snapshots** (`raw_data/crm_customers/customers_YYYYMMDD.csv`)
   — one full extract per day for a 14-day window. A documented ~3% of
   customers change `plan_id`, `region`, or `segment` between consecutive
   days — this is the raw material `dbt/snapshots/customer_snapshot.sql`
   turns into `dim_customer`'s SCD Type 2 history. Without genuine
   day-to-day changes here, SCD2 would have nothing to demonstrate.

2. **Billing extract** (`raw_data/invoices.csv`) — one incremental pull
   covering the same 14-day window, deliberately messy:
   - ~2% exact duplicate `invoice_id` rows (a re-pulled/re-submitted record)
   - ~1.5% orphan `customer_id`s that never appear in any CRM snapshot
     (a deleted/test account, or a billing-system-only customer)
   - ~2% negative or null `amount` (a refund processed as a negative
     invoice, or a failed charge with no amount captured)
   - ~2% invoices dated *before* the CRM snapshot window even starts —
     genuinely existing customers, but the invoice predates the earliest
     day dim_customer has SCD2 coverage for (late-arriving billing data,
     or a backfill from a legacy system) — this is what the temporal
     referential-integrity test in dbt is built to catch; it is not the
     same failure mode as an orphan customer_id.

3. **Product usage events** (`raw_data/usage_events.csv`) — ~20,000 events
   across the same window, weighted toward paying customers. Left clean
   (no injected messiness) — the point of this source is volume for
   `fact_usage_daily`, not another data-quality demonstration.

`raw_data/plans.csv` is a small, clean, static reference table.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

RNG_SEED = 42
N_CUSTOMERS = 500
N_SNAPSHOT_DAYS = 14
DAILY_CHANGE_RATE = 0.03  # fraction of customers whose plan/region/segment changes each day

RAW_DIR = Path(__file__).resolve().parent.parent / "raw_data"
CRM_DIR = RAW_DIR / "crm_customers"

TODAY = date(2026, 8, 16)
SNAPSHOT_START = TODAY - timedelta(days=N_SNAPSHOT_DAYS - 1)

PLANS = [
    # plan_id, plan_name, monthly_price, tier
    ("PLAN-STARTER", "Starter", 29.00, "starter"),
    ("PLAN-GROWTH", "Growth", 99.00, "growth"),
    ("PLAN-SCALE", "Scale", 299.00, "scale"),
    ("PLAN-ENTERPRISE", "Enterprise", 999.00, "enterprise"),
]

REGIONS = ["London", "South East", "North West", "Scotland", "Wales", "Yorkshire", "South West"]
SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]

FIRST_NAMES = ["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie",
               "Charlie", "Priya", "Wei", "Fatima", "Liam", "Olivia", "Noah", "Ava"]
LAST_NAMES = ["Smith", "Jones", "Khan", "Patel", "Brown", "Wilson", "Taylor", "Evans",
              "Roberts", "Walker", "Hughes", "Green", "Murray", "Campbell", "Baker"]
COMPANY_SUFFIXES = ["Ltd", "Group", "Solutions", "Digital", "Labs", "Partners", "& Co"]


def _random_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _random_company(rng: random.Random, idx: int) -> str:
    return f"{rng.choice(LAST_NAMES)} {rng.choice(COMPANY_SUFFIXES)} {idx}"


def _build_customers(rng: random.Random) -> list[dict]:
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        customer_id = f"CUST{i:05d}"
        signup_date = SNAPSHOT_START - timedelta(days=rng.randint(1, 540))
        name = _random_name(rng)
        customers.append({
            "customer_id": customer_id,
            "name": name,
            "email": name.lower().replace(" ", ".") + f"{i}@example.com",
            "company": _random_company(rng, i),
            "plan_id": rng.choice(PLANS)[0],
            "region": rng.choice(REGIONS),
            "segment": rng.choices(SEGMENTS, weights=[0.6, 0.3, 0.1])[0],
            "signup_date": signup_date.isoformat(),
        })
    return customers


def _apply_daily_changes(customers: list[dict], rng: random.Random) -> int:
    """Mutates a documented fraction of customers in place (plan/region/
    segment) and returns how many changed, for a sanity-check print."""
    plan_ids = [p[0] for p in PLANS]
    n_changed = 0
    for c in customers:
        if rng.random() < DAILY_CHANGE_RATE:
            field = rng.choice(["plan_id", "region", "segment"])
            if field == "plan_id":
                c["plan_id"] = rng.choice([p for p in plan_ids if p != c["plan_id"]])
            elif field == "region":
                c["region"] = rng.choice([r for r in REGIONS if r != c["region"]])
            else:
                c["segment"] = rng.choice([s for s in SEGMENTS if s != c["segment"]])
            n_changed += 1
    return n_changed


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def _generate_crm_snapshots(rng: random.Random, customers: list[dict]) -> None:
    header = ["customer_id", "name", "email", "company", "plan_id", "region", "segment",
              "signup_date", "snapshot_date"]
    total_changes = 0
    for day_offset in range(N_SNAPSHOT_DAYS):
        snapshot_date = SNAPSHOT_START + timedelta(days=day_offset)
        if day_offset > 0:
            total_changes += _apply_daily_changes(customers, rng)
        rows = [{**c, "snapshot_date": snapshot_date.isoformat()} for c in customers]
        _write_csv(CRM_DIR / f"customers_{snapshot_date.strftime('%Y%m%d')}.csv", header, rows)
    print(f"CRM snapshots: {N_SNAPSHOT_DAYS} days, {total_changes} plan/region/segment "
          f"changes across the window ({total_changes / ((N_SNAPSHOT_DAYS - 1) * N_CUSTOMERS):.1%} "
          f"of customer-days)")


def _generate_invoices(rng: random.Random, customers: list[dict]) -> None:
    plan_price = {p[0]: p[2] for p in PLANS}
    header = ["invoice_id", "customer_id", "plan_id", "invoice_date", "amount", "status"]
    rows = []
    invoice_counter = 1

    for c in customers:
        n_invoices = rng.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
        for _ in range(n_invoices):
            invoice_date = SNAPSHOT_START + timedelta(days=rng.randint(0, N_SNAPSHOT_DAYS - 1))
            price = plan_price[c["plan_id"]]
            amount = round(price * rng.uniform(0.95, 1.05), 2)
            status = rng.choices(["paid", "failed", "refunded"], weights=[0.90, 0.06, 0.04])[0]
            rows.append({
                "invoice_id": f"INV{invoice_counter:06d}",
                "customer_id": c["customer_id"],
                "plan_id": c["plan_id"],
                "invoice_date": invoice_date.isoformat(),
                "amount": amount,
                "status": status,
            })
            invoice_counter += 1

    n_base = len(rows)

    # ~2% exact duplicate invoice_id rows (re-pulled/re-submitted record).
    n_dupes = max(1, round(n_base * 0.02))
    for row in rng.sample(rows, n_dupes):
        rows.append(dict(row))

    # ~1.5% orphan customer_id (never appears in any CRM snapshot).
    n_orphans = max(1, round(n_base * 0.015))
    for i in range(n_orphans):
        invoice_date = SNAPSHOT_START + timedelta(days=rng.randint(0, N_SNAPSHOT_DAYS - 1))
        plan_id = rng.choice(PLANS)[0]
        rows.append({
            "invoice_id": f"INV{invoice_counter:06d}",
            "customer_id": f"CUST-DELETED-{i:03d}",
            "plan_id": plan_id,
            "invoice_date": invoice_date.isoformat(),
            "amount": round(plan_price[plan_id] * rng.uniform(0.95, 1.05), 2),
            "status": "paid",
        })
        invoice_counter += 1

    # ~2% negative or null amount.
    n_bad_amount = max(1, round(n_base * 0.02))
    for row in rng.sample(rows[:n_base], n_bad_amount):
        row["amount"] = "" if rng.random() < 0.5 else -abs(row["amount"])

    # ~2% invoices dated before the CRM snapshot window starts (late-arriving /
    # predates dim_customer's earliest SCD2 coverage) — existing customers,
    # but a temporal referential-integrity violation, not an orphan.
    n_late = max(1, round(n_base * 0.02))
    for row in rng.sample(rows[:n_base], n_late):
        row["invoice_date"] = (SNAPSHOT_START - timedelta(days=rng.randint(3, 10))).isoformat()

    rng.shuffle(rows)
    _write_csv(RAW_DIR / "invoices.csv", header, rows)
    print(f"Invoices: {n_base} base rows -> {len(rows)} total "
          f"({n_dupes} duplicates, {n_orphans} orphan customers, {n_bad_amount} bad amounts, "
          f"{n_late} pre-window/late-arriving)")


def _generate_usage_events(rng: random.Random, customers: list[dict]) -> None:
    header = ["event_id", "customer_id", "event_type", "event_timestamp", "feature_used"]
    event_types = ["login", "api_call", "export", "dashboard_view", "report_generated"]
    features = ["billing", "analytics", "integrations", "team_management", "api"]

    # weight events toward paying (non-starter) customers, a light behavioural signal
    weights = [3.0 if c["plan_id"] != "PLAN-STARTER" else 1.0 for c in customers]

    rows = []
    n_events = 20_000
    for i in range(1, n_events + 1):
        customer = rng.choices(customers, weights=weights, k=1)[0]
        day_offset = rng.randint(0, N_SNAPSHOT_DAYS - 1)
        ts = SNAPSHOT_START + timedelta(days=day_offset, seconds=rng.randint(0, 86399))
        rows.append({
            "event_id": f"EVT{i:07d}",
            "customer_id": customer["customer_id"],
            "event_type": rng.choice(event_types),
            "event_timestamp": ts.isoformat(),
            "feature_used": rng.choice(features),
        })

    _write_csv(RAW_DIR / "usage_events.csv", header, rows)
    print(f"Usage events: {len(rows)} rows across {N_SNAPSHOT_DAYS} days")


def _generate_plans() -> None:
    header = ["plan_id", "plan_name", "monthly_price", "tier"]
    rows = [
        {"plan_id": p[0], "plan_name": p[1], "monthly_price": p[2], "tier": p[3]} for p in PLANS
    ]
    _write_csv(RAW_DIR / "plans.csv", header, rows)
    print(f"Plans: {len(rows)} rows")


def generate(seed: int = RNG_SEED) -> None:
    rng = random.Random(seed)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    _generate_plans()
    customers = _build_customers(rng)
    _generate_crm_snapshots(rng, customers)  # mutates `customers` day by day
    _generate_invoices(rng, customers)
    _generate_usage_events(rng, customers)


if __name__ == "__main__":
    generate()
