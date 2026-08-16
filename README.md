# SaaS Subscription Data Platform

[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![Dagster](https://img.shields.io/badge/Dagster-1.13-6E37F5)](https://dagster.io/)
[![dbt](https://img.shields.io/badge/dbt-1.11-FF694B)](https://www.getdbt.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.5-FFF000)](https://duckdb.org/)
[![tests](https://img.shields.io/badge/tests-17%20passing-brightgreen)](tests/)

A Dagster-orchestrated dbt pipeline turning three messy SaaS source
extracts (CRM, billing, product usage) into a star schema with an SCD Type
2 customer dimension and a Monthly Recurring Revenue mart — end to end,
from raw CSV to a single unified Dagster lineage graph, with 46 dbt tests
and 17 Python tests, all executed for real.

**Dataset:** synthetic but structurally realistic — 500 customers, 14 days
of daily CRM snapshots, ~860 billing records, 20,000 product-usage events,
generated with a fixed seed (`data_gen/generate_source_data.py`). Every
messiness pattern is deliberate and documented: genuine day-to-day
plan/region/segment changes (the raw material for SCD2), duplicate
invoice IDs, orphan customer references, null/negative amounts, and
invoices dated before a customer's earliest CRM record (late-arriving
data).

**Stack:** Python 3.11 · Dagster (asset-based orchestration) · dbt-core +
dbt-duckdb · DuckDB (local, file-based warehouse) · pytest

---

## Why this project

1. **This is the only pipeline-orchestration project in the portfolio.**
   Every other repo here — SQL analytics, funnel/cohort, Excel cleaning,
   the ML-serving API — either analyses data in place or serves a trained
   model; none of them ingest, transform, and schedule data through a
   dimensional model. This one does, end to end.
2. **SCD Type 2 reconstructed from pre-collected daily snapshots is a
   different problem than dbt's `snapshot` feature solves**, and the
   distinction matters: `snapshot` captures a live source's current state
   once per real dbt invocation, accumulating history over days/weeks of
   repeated runs. Here the 14 days of history already exist in one raw
   table from a single extract, so `int_customer_history.sql` reconstructs
   versions with a single-pass window-function "gaps and islands" query
   instead — the correct tool for this specific data shape, not a
   simplification.
3. **Nothing is silently dropped.** Duplicate invoice IDs are deduplicated
   with a documented rule; bad amounts are reclassified to
   `flagged_for_review` rather than deleted; invoices that can't be
   resolved to a valid customer dimension row are routed to
   `fact_invoice_rejected`, a queryable quarantine table, not discarded.
   `fact_invoice`'s own dbt tests are designed to always pass *because*
   this routing is correct — the injected bad rows are still fully
   traceable, just not left where they'd corrupt an MRR calculation.

---

## Architecture

```
raw_data/ (CSV)                    Dagster                          dbt (DuckDB)
├── crm_customers/*.csv  ───▶  raw_crm_customers  ───┐
├── plans.csv             ───▶  raw_plans          ───┤    stg_*  ──▶  int_customer_history
├── invoices.csv          ───▶  raw_invoices        ───┤              ──▶ int_customer_scd ──▶ dim_customer
└── usage_events.csv      ───▶  raw_usage_events    ───┘              int_invoice_resolved ──▶ fact_invoice
                                       │                                                     └▶ fact_invoice_rejected
                                       ▼                               dim_plan, dim_date
                              saas_dbt_assets (dbt build)              fact_usage_daily
                                       │                                mrr_monthly
                                       ▼
                            pipeline_health_report (volume/quarantine checks)
```

A custom `DagsterDbtTranslator` (`dagster_project/dbt_translator.py`) maps
each dbt `source` node onto this project's own raw-ingestion asset key
(`raw_plans`, `raw_crm_customers`, ...), so Dagster renders **one**
lineage graph from CSV to mart — not two disconnected halves (Python
assets and dbt's internal DAG) glued together only by coincidence of
running in the same job.

---

## Project Structure

```
saas-subscription-data-platform/
├── data_gen/
│   └── generate_source_data.py   # synthetic CRM/billing/usage extracts, documented messiness, fixed seed
├── dagster_project/
│   ├── ingestion.py               # raw CSV -> DuckDB `raw` schema (plain functions, reused by assets + standalone)
│   ├── assets.py                  # raw_* ingestion assets + the dbt asset group
│   ├── dbt_translator.py          # unifies dbt sources with the raw_* asset keys
│   ├── data_quality.py            # from-scratch volume z-score + quarantine-rate checks
│   ├── health_asset.py            # runs the checks post-dbt-build, writes outputs/dq_report.json
│   └── definitions.py             # wires assets + daily schedule + the dbt resource
├── dbt/
│   ├── models/staging/            # typed, deduplicated, flagged -- nothing dropped
│   ├── models/intermediate/       # SCD2 reconstruction (window functions) + temporal invoice join
│   ├── models/marts/              # dim_customer, dim_plan, dim_date, fact_invoice(+_rejected), fact_usage_daily, mrr_monthly
│   ├── tests/                     # 3 custom singular tests -- see Results
│   └── dbt_project.yml
├── tests/                         # 17 pytest tests: generator determinism/patterns, DQ-check unit tests
└── pyproject.toml
```

---

## Results (real, from an executed run)

### Data quality, end to end

| Stage | Input | Output | What happened |
|---|---|---|---|
| Dedup | 858 raw invoice rows | 841 after dedup | 17 exact-duplicate `invoice_id` rows collapsed to one each |
| Resolution | 841 deduplicated invoices | 812 in `fact_invoice`, 29 in `fact_invoice_rejected` | 12 orphan `customer_id`s + 17 invoices predating the customer's earliest SCD2 coverage — **both counts match the generator's injected rates exactly** |
| Amount flagging | — | 17 rows `status_clean = 'flagged_for_review'` | matches the ~2% injected null/negative amounts |

**46/46 dbt tests pass**, including 3 custom singular tests that are the
actual point of this repo, not generic key checks:

- `assert_no_overlapping_scd2_ranges` — a correctness *invariant* on
  `dim_customer` (should always pass by construction; proves the
  window-function SCD2 logic doesn't produce overlapping versions).
- `assert_paid_invoices_non_negative` — passes because `fact_invoice.sql`
  reclassifies bad-amount rows before this test ever sees them, not by
  coincidence.
- `assert_fact_invoice_fully_resolved` — passes because unresolved rows
  are routed to `fact_invoice_rejected`, not because there weren't any
  (there were 29 — see the table above).

### SCD Type 2

500 customers → **703 dimension versions** in `dim_customer` (162
customers changed plan/region/segment at least once across the 14-day
window — 3.1% of customer-days, matching the generator's documented
`DAILY_CHANGE_RATE`).

### mrr_monthly

12 rows (4 plan tiers × 3 segments), computed only from `status_clean =
'paid'` invoices — the flagged-for-review rows are excluded from revenue
on purpose, not averaged in. Real numbers from the executed run, e.g.
Enterprise/Enterprise-segment: 78 paying customers, £120,577.79 MRR,
£1,545.87 ARPU.

---

## Quickstart

```bash
# 1. install (creates its own .venv-friendly dependency set — dagster + dbt + duckdb are heavier than this portfolio's usual footprint)
pip install -e ".[dev]"

# 2. generate the synthetic source data (fixed seed -- deterministic)
python3 data_gen/generate_source_data.py

# 3. build the dbt manifest dagster_dbt needs to define the asset graph
#    (dagster dev auto-builds this; `dagster job execute` / CI does not,
#    so this step is required the first time or after a schema change)
cd dbt && dbt parse --profiles-dir . && cd ..

# 4. run the whole pipeline once, end to end
DAGSTER_HOME="$(pwd)/.dagster_home" dagster job execute -j daily_pipeline_job -m dagster_project.definitions

# 5. or launch the Dagster UI and materialize interactively
DAGSTER_HOME="$(pwd)/.dagster_home" dagster dev -m dagster_project.definitions

# 6. run the tests
pytest tests/ -v
```

---

## Technical Notes

- **DuckDB is single-writer.** Dagster's default multiprocess executor
  runs independent assets (the 4 `raw_*` ingestion assets have no
  dependencies on each other) in parallel subprocesses — which collide on
  DuckDB's file lock. Fixed with `executor_def=dg.in_process_executor` on
  the job, the standard fix for a DuckDB-backed Dagster project this size;
  a client/server warehouse would be over-engineering for a single-file
  local warehouse whose entire point is zero-infrastructure portability.
- **A real bug found while writing tests, not just running them:**
  `volume_zscore_report`'s original leave-one-out z-score set `z = 0.0`
  whenever the *other* days had zero variance (`std == 0`) — which, for a
  perfectly-consistent daily row count, is exactly the case that should
  make *any* deviation maximally anomalous, not invisible to the check.
  `tests/test_data_quality.py::test_volume_zscore_flags_a_dropped_day`
  caught it; fixed to treat a deviation from a zero-variance baseline as
  an extreme (not zero) z-score.
- **`dagster_dbt`'s `prepare_if_dev()` only auto-builds the dbt manifest
  under `dagster dev`'s dev-CLI context** — `dagster job execute` and any
  CI-style run expect `dbt/target/manifest.json` to already exist (built
  via `dbt parse`/`dbt build` ahead of time), the standard dagster-dbt
  production pattern. Documented explicitly in Quickstart rather than
  left as a trap.
- **`fact_invoice_rejected` is a deliberate design choice, not a
  workaround.** Distinguishing `orphan_customer_id` from
  `invoice_predates_scd_coverage` needs different fixes in a real system
  (a genuinely deleted customer vs. a backfill/late-arrival problem) — one
  generic "unresolved" bucket would have hidden that they're different
  problems.
