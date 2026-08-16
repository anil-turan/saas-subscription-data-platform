import sys
from pathlib import Path

import dagster as dg
from dagster_dbt import DbtCliResource

from .assets import raw_crm_customers, raw_invoices, raw_plans, raw_usage_events, saas_dbt_assets
from .health_asset import pipeline_health_report
from .project import dbt_project

# Resolve the `dbt` CLI from the same virtualenv running this process,
# rather than relying on `dbt` being on PATH (it isn't, unless the venv is
# actively activated).
_dbt_executable = Path(sys.executable).parent / "dbt"

all_assets = [
    raw_plans,
    raw_crm_customers,
    raw_invoices,
    raw_usage_events,
    saas_dbt_assets,
    pipeline_health_report,
]

# DuckDB is a single-writer, single-process database -- Dagster's default
# multiprocess executor runs independent assets (the 4 raw_* ingestion
# assets have no dependencies on each other) in parallel subprocesses,
# which collide on the .duckdb file lock. in_process_executor runs the
# whole job sequentially in one process, which is the standard fix for a
# DuckDB-backed Dagster project this size (see e.g. dagster-io/dagster's
# own DuckDB example projects) -- the alternative (giving each asset its
# own duckdb file, or a real client/server warehouse) would be over-
# engineering for a single-writer local warehouse.
daily_pipeline_job = dg.define_asset_job(
    name="daily_pipeline_job", selection=all_assets, executor_def=dg.in_process_executor
)

# Documents how this would run in production -- a nightly pull after the
# CRM/billing/usage source systems have finished their own overnight batch.
# Same convention as this portfolio's other pipelines/notebooks: executed
# once for real to produce genuine results, not run continuously on a live
# clock inside this repo.
daily_schedule = dg.ScheduleDefinition(
    job=daily_pipeline_job,
    cron_schedule="0 5 * * *",
)

defs = dg.Definitions(
    assets=all_assets,
    schedules=[daily_schedule],
    resources={"dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=str(_dbt_executable))},
)
