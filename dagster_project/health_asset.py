import json
from pathlib import Path

import dagster as dg
import duckdb

from .assets import saas_dbt_assets
from .data_quality import quarantine_rate_report, volume_zscore_report
from .ingestion import WAREHOUSE_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "outputs" / "dq_report.json"


@dg.asset(deps=[saas_dbt_assets], group_name="data_quality", compute_kind="python")
def pipeline_health_report() -> dg.MaterializeResult:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    try:
        daily_counts = dict(
            con.execute(
                "select snapshot_date::varchar, count(*) from raw.crm_customers group by 1"
            ).fetchall()
        )
        total_invoices = con.execute(
            "select (select count(*) from fact_invoice) "
            "+ (select count(*) from fact_invoice_rejected)"
        ).fetchone()[0]
        quarantined_invoices = con.execute(
            "select count(*) from fact_invoice_rejected"
        ).fetchone()[0]
    finally:
        con.close()

    report = {
        "crm_snapshot_volume": volume_zscore_report(daily_counts),
        "invoice_quarantine_rate": quarantine_rate_report(total_invoices, quarantined_invoices),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2))

    overall_status = (
        "alert"
        if "alert" in (report["crm_snapshot_volume"]["status"],)
        or "warn" in (report["invoice_quarantine_rate"]["status"],)
        else "ok"
    )
    return dg.MaterializeResult(
        metadata={
            "overall_status": overall_status,
            "crm_snapshot_volume_status": report["crm_snapshot_volume"]["status"],
            "invoice_quarantine_rate": report["invoice_quarantine_rate"]["quarantine_rate"],
            "report_path": str(OUTPUT_PATH),
        }
    )
