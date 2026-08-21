"""Render the two README figures from the executed warehouse.

Reads `warehouse.duckdb` (built by the pipeline -- run it first) and writes
PNGs to `docs/images/`. Nothing is hard-coded: every number in the charts is
queried, so the figures cannot drift away from what the pipeline actually
produced.

    python3 docs/make_readme_charts.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

REPO_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = REPO_ROOT / "warehouse.duckdb"
IMAGE_DIR = Path(__file__).resolve().parent / "images"

SURFACE = "#ffffff"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED = "#e34948"
AMBER = "#eda100"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "text.color": TEXT_PRIMARY,
        "axes.labelcolor": TEXT_SECONDARY,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def _money(value: float) -> str:
    """£1,546 below a thousand, £12.9k / £121k above -- never a rounded-away '£0k'."""
    if value < 1_000:
        return f"£{value:,.0f}"
    if value < 10_000:
        return f"£{value/1000:,.1f}k"
    return f"£{value/1000:,.0f}k"


def _style_axes(ax) -> None:
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRID)
    ax.tick_params(length=0)


def invoice_pipeline_chart(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Every invoice row, from raw CSV to its final resting place."""
    raw = con.execute("select count(*) from raw.invoices").fetchone()[0]
    deduped = con.execute("select count(*) from stg_invoices").fetchone()[0]
    resolved = con.execute("select count(*) from fact_invoice").fetchone()[0]
    flagged = con.execute(
        "select count(*) from fact_invoice where status_clean = 'flagged_for_review'"
    ).fetchone()[0]
    rejected = dict(
        con.execute(
            "select rejection_reason, count(*) from fact_invoice_rejected group by 1"
        ).fetchall()
    )

    stages = [
        ("raw.invoices\n(source extract)", raw, BLUE, f"{raw:,} rows"),
        (
            "stg_invoices\n(after dedup)",
            deduped,
            BLUE,
            f"{deduped:,}  ·  {raw - deduped} duplicate IDs collapsed",
        ),
        (
            "fact_invoice\n(resolved to SCD2)",
            resolved,
            AQUA,
            f"{resolved:,}  ·  {flagged} flagged_for_review, excluded from MRR",
        ),
        (
            "fact_invoice_rejected\n(quarantine)",
            sum(rejected.values()),
            RED,
            "  ·  ".join(f"{n} {reason}" for reason, n in sorted(rejected.items())),
        ),
    ]

    fig, ax = plt.subplots(figsize=(10, 4.2))
    labels = [s[0] for s in stages]
    values = [s[1] for s in stages]
    colors = [s[2] for s in stages]
    ypos = range(len(stages))

    ax.barh(list(ypos), values, color=colors, height=0.55, zorder=3)
    for y, (_, value, _, note) in enumerate(stages):
        ax.text(
            value + raw * 0.015,
            y,
            note,
            va="center",
            ha="left",
            fontsize=9,
            color=TEXT_SECONDARY,
        )

    ax.set_yticks(list(ypos), labels, fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xlim(0, raw * 1.55)
    ax.set_xticks([])
    ax.set_title(
        "Nothing is silently dropped: every invoice row is accounted for",
        loc="left",
        pad=34,
        fontweight="bold",
    )
    ax.text(
        0,
        1.03,
        "Rejected rows stay queryable in a quarantine table, split by cause —\n"
        "a deleted customer and a late-arriving invoice need different fixes.",
        transform=ax.transAxes,
        fontsize=9,
        color=TEXT_SECONDARY,
        va="bottom",
        linespacing=1.4,
    )
    _style_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)

    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def mrr_chart(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    """The mart's actual output: MRR by plan tier, split by customer segment."""
    rows = con.execute(
        """
        select plan_name, segment, mrr, paying_customers
        from mrr_monthly
        order by plan_name, segment
        """
    ).fetchall()

    plans = ["Starter", "Growth", "Scale", "Enterprise"]
    segments = ["SMB", "Mid-Market", "Enterprise"]
    colors = {"SMB": BLUE, "Mid-Market": ORANGE, "Enterprise": AQUA}
    lookup = {(p, s): (float(m), c) for p, s, m, c in rows}

    fig, ax = plt.subplots(figsize=(10, 4.6))
    width = 0.26
    for i, segment in enumerate(segments):
        offsets = [x + (i - 1) * (width + 0.015) for x in range(len(plans))]
        values = [lookup[(p, segment)][0] for p in plans]
        ax.bar(
            offsets,
            values,
            width=width,
            label=segment,
            color=colors[segment],
            zorder=3,
        )
        for x, value, plan in zip(offsets, values, plans):
            customers = lookup[(plan, segment)][1]
            ax.text(
                x,
                value + 2500,
                f"{_money(value)}\n{customers} cust.",
                ha="center",
                va="bottom",
                fontsize=8,
                color=TEXT_SECONDARY,
                linespacing=1.3,
            )

    ax.set_xticks(range(len(plans)), plans)
    ax.tick_params(axis="x", pad=8)
    ax.set_ylabel("Monthly recurring revenue")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"£{v/1000:,.0f}k"))
    ax.set_ylim(0, max(v for v, _ in lookup.values()) * 1.22)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(
        title="Customer segment",
        frameon=False,
        loc="upper left",
        title_fontsize=9,
        fontsize=9,
    )
    ax.set_title(
        "mrr_monthly: revenue by plan tier and customer segment",
        loc="left",
        pad=34,
        fontweight="bold",
    )
    ax.text(
        0,
        1.03,
        "Paid invoices only — rows flagged for a null or negative amount are\n"
        "excluded from revenue rather than averaged in.",
        transform=ax.transAxes,
        fontsize=9,
        color=TEXT_SECONDARY,
        va="bottom",
        linespacing=1.4,
    )
    _style_axes(ax)

    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main() -> None:
    if not WAREHOUSE.exists():
        raise SystemExit(
            f"{WAREHOUSE} not found — run the pipeline first (see README Quickstart)."
        )
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        invoice_pipeline_chart(con, IMAGE_DIR / "invoice_pipeline.png")
        mrr_chart(con, IMAGE_DIR / "mrr_monthly.png")
    finally:
        con.close()
    print(f"Wrote figures to {IMAGE_DIR}")


if __name__ == "__main__":
    main()
