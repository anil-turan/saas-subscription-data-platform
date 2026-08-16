import dagster as dg
from dagster_dbt import DbtCliResource, dbt_assets

from . import ingestion
from .dbt_translator import SaasDagsterDbtTranslator
from .project import dbt_project


@dg.asset(group_name="raw_ingestion", compute_kind="python")
def raw_plans() -> dg.MaterializeResult:
    n = ingestion.load_plans()
    return dg.MaterializeResult(metadata={"rows_loaded": n})


@dg.asset(group_name="raw_ingestion", compute_kind="python")
def raw_crm_customers() -> dg.MaterializeResult:
    n = ingestion.load_crm_customers()
    return dg.MaterializeResult(metadata={"rows_loaded": n})


@dg.asset(group_name="raw_ingestion", compute_kind="python")
def raw_invoices() -> dg.MaterializeResult:
    n = ingestion.load_invoices()
    return dg.MaterializeResult(metadata={"rows_loaded": n})


@dg.asset(group_name="raw_ingestion", compute_kind="python")
def raw_usage_events() -> dg.MaterializeResult:
    n = ingestion.load_usage_events()
    return dg.MaterializeResult(metadata={"rows_loaded": n})


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=SaasDagsterDbtTranslator())
def saas_dbt_assets(context: dg.AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
