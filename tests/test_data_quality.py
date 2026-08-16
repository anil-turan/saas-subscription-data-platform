"""Tests for the from-scratch pipeline-health checks."""

from dagster_project.data_quality import quarantine_rate_report, volume_zscore_report


def test_volume_zscore_stable_days_no_anomaly():
    counts = {f"2026-08-{d:02d}": 500 for d in range(1, 15)}
    report = volume_zscore_report(counts)
    assert report["status"] == "ok"
    assert report["anomalies"] == []


def test_volume_zscore_flags_a_dropped_day():
    counts = {f"2026-08-{d:02d}": 500 for d in range(1, 15)}
    counts["2026-08-07"] = 50  # a genuine partial-load day
    report = volume_zscore_report(counts)
    assert report["status"] == "alert"
    assert any(a["date"] == "2026-08-07" for a in report["anomalies"])


def test_volume_zscore_leave_one_out_does_not_mask_the_anomaly_itself():
    """A naive z-score (including the anomaly in its own mean/std) can
    understate how extreme an outlier is; leave-one-out compares each day
    only against the OTHER days."""
    counts = {f"2026-08-{d:02d}": 500 for d in range(1, 15)}
    counts["2026-08-07"] = 0
    report = volume_zscore_report(counts)
    flagged = next(a for a in report["anomalies"] if a["date"] == "2026-08-07")
    assert abs(flagged["z_score"]) > 5


def test_volume_zscore_threshold_is_configurable():
    # Realistic day-to-day variance in the reference days (not a perfectly
    # constant baseline) -- with zero variance elsewhere, ANY deviation is
    # correctly treated as infinitely anomalous regardless of threshold,
    # which isn't what this test is exercising.
    base = [495, 505, 498, 502, 500, 497, 503, 499, 501, 496, 504, 500, 498]
    counts = {f"2026-08-{d:02d}": v for d, v in zip(range(1, 14), base)}
    counts["2026-08-14"] = 490  # a somewhat low but not extreme day
    strict = volume_zscore_report(counts, z_threshold=1.0)
    lenient = volume_zscore_report(counts, z_threshold=5.0)
    assert strict["status"] == "alert"
    assert lenient["status"] == "ok"


def test_quarantine_rate_below_threshold_is_ok():
    report = quarantine_rate_report(total_rows=1000, quarantined_rows=20, warn_threshold=0.05)
    assert report["status"] == "ok"
    assert report["quarantine_rate"] == 0.02


def test_quarantine_rate_above_threshold_warns():
    report = quarantine_rate_report(total_rows=1000, quarantined_rows=80, warn_threshold=0.05)
    assert report["status"] == "warn"
    assert report["quarantine_rate"] == 0.08


def test_quarantine_rate_handles_zero_total_rows():
    report = quarantine_rate_report(total_rows=0, quarantined_rows=0)
    assert report["quarantine_rate"] == 0.0
    assert report["status"] == "ok"
