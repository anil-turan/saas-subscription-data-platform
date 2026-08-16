"""Maps dbt's `raw` sources onto this project's own raw-ingestion asset
keys (raw_plans, raw_crm_customers, ...) so Dagster shows ONE unified
lineage graph from CSV to mart, instead of the raw ingestion assets and
dbt's source nodes appearing as two disconnected halves."""

import dagster as dg
from dagster_dbt import DagsterDbtTranslator


class SaasDagsterDbtTranslator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "source":
            return dg.AssetKey(f"raw_{dbt_resource_props['name']}")
        return super().get_asset_key(dbt_resource_props)
