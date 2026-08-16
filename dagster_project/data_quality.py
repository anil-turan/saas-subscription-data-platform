"""From-scratch pipeline-health checks -- the same statistical instinct as
this portfolio's PSI/KS model-drift monitors (see e.g.
credit-risk-ml-pipeline/src/credit_risk/monitoring/drift.py), applied here
to pipeline *volume and quarantine rate* instead of a model's score
distribution. A model can be silently wrong; so can a pipeline that loads
half its usual row count with no error thrown.
"""

from __future__ import annotations

import numpy as np


def volume_zscore_report(daily_counts: dict[str, int], z_threshold: float = 2.0) -> dict:
    """Flags any day whose row count is more than `z_threshold` standard
    deviations from the mean of the OTHER days (leave-one-out z-score, so
    a single genuinely anomalous day can't inflate the mean it's being
    compared against and mask itself)."""
    dates = sorted(daily_counts)
    values = np.array([daily_counts[d] for d in dates], dtype=float)

    anomalies = []
    for i, d in enumerate(dates):
        others = np.delete(values, i)
        mean, std = others.mean(), others.std()
        if std == 0:
            # The other days are perfectly constant -- any deviation at all
            # is anomalous by definition, not a "no signal, treat as 0" case.
            z = 0.0 if values[i] == mean else (999.0 if values[i] > mean else -999.0)
        else:
            z = (values[i] - mean) / std
        if abs(z) > z_threshold:
            anomalies.append({"date": d, "count": int(values[i]), "z_score": round(float(z), 2)})

    return {
        "n_days_checked": len(dates),
        "mean_count": round(float(values.mean()), 1) if len(values) else 0.0,
        "std_count": round(float(values.std()), 1) if len(values) else 0.0,
        "anomalies": anomalies,
        "status": "alert" if anomalies else "ok",
    }


def quarantine_rate_report(
    total_rows: int, quarantined_rows: int, warn_threshold: float = 0.05
) -> dict:
    """A rising fact_invoice_rejected rate is exactly the kind of thing
    that's easy to miss if nobody's looking at row counts -- this turns it
    into a monitored, thresholded number."""
    rate = quarantined_rows / total_rows if total_rows else 0.0
    return {
        "total_rows": total_rows,
        "quarantined_rows": quarantined_rows,
        "quarantine_rate": round(rate, 4),
        "status": "warn" if rate > warn_threshold else "ok",
    }
