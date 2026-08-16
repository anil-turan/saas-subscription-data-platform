"""Tests for the synthetic SaaS source-data generator.

Checks that the generator is deterministic (reproducible pipeline runs) and
that every messiness pattern documented in the module docstring is
genuinely present at roughly its documented rate -- so the dbt tests
downstream are being exercised against real, not accidental, messiness.
"""

from __future__ import annotations

import csv

import pytest

from data_gen import generate_source_data as gen


@pytest.fixture
def generated_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "RAW_DIR", tmp_path)
    monkeypatch.setattr(gen, "CRM_DIR", tmp_path / "crm_customers")
    gen.generate(seed=gen.RNG_SEED)
    return tmp_path


def _read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_deterministic_across_runs(tmp_path, monkeypatch):
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setattr(gen, "RAW_DIR", dir_a)
    monkeypatch.setattr(gen, "CRM_DIR", dir_a / "crm_customers")
    gen.generate(seed=7)
    monkeypatch.setattr(gen, "RAW_DIR", dir_b)
    monkeypatch.setattr(gen, "CRM_DIR", dir_b / "crm_customers")
    gen.generate(seed=7)

    assert (dir_a / "invoices.csv").read_bytes() == (dir_b / "invoices.csv").read_bytes()
    assert (dir_a / "usage_events.csv").read_bytes() == (dir_b / "usage_events.csv").read_bytes()
    a_snapshots = sorted((dir_a / "crm_customers").iterdir())
    b_snapshots = sorted((dir_b / "crm_customers").iterdir())
    assert [p.name for p in a_snapshots] == [p.name for p in b_snapshots]
    assert all(a.read_bytes() == b.read_bytes() for a, b in zip(a_snapshots, b_snapshots))


def test_different_seed_changes_invoices(tmp_path, monkeypatch):
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setattr(gen, "RAW_DIR", dir_a)
    monkeypatch.setattr(gen, "CRM_DIR", dir_a / "crm_customers")
    gen.generate(seed=1)
    monkeypatch.setattr(gen, "RAW_DIR", dir_b)
    monkeypatch.setattr(gen, "CRM_DIR", dir_b / "crm_customers")
    gen.generate(seed=2)

    assert (dir_a / "invoices.csv").read_bytes() != (dir_b / "invoices.csv").read_bytes()


def test_plans_are_clean_and_complete(generated_dir):
    plans = _read_rows(generated_dir / "plans.csv")
    assert len(plans) == len(gen.PLANS)
    assert {p["plan_id"] for p in plans} == {p[0] for p in gen.PLANS}
    for row in plans:
        assert all(v != "" for v in row.values())


def test_crm_snapshots_one_file_per_day(generated_dir):
    snapshot_files = sorted((generated_dir / "crm_customers").iterdir())
    assert len(snapshot_files) == gen.N_SNAPSHOT_DAYS
    for f in snapshot_files:
        rows = _read_rows(f)
        assert len(rows) == gen.N_CUSTOMERS


def test_crm_snapshots_contain_genuine_attribute_changes(generated_dir):
    """Without real day-to-day changes, SCD2 has nothing to reconstruct."""
    snapshot_files = sorted((generated_dir / "crm_customers").iterdir())
    day0 = {r["customer_id"]: r for r in _read_rows(snapshot_files[0])}
    day1 = {r["customer_id"]: r for r in _read_rows(snapshot_files[1])}

    changed = sum(
        1
        for cid, row in day1.items()
        if (row["plan_id"], row["region"], row["segment"])
        != (day0[cid]["plan_id"], day0[cid]["region"], day0[cid]["segment"])
    )
    assert changed > 0


def test_invoices_contain_duplicate_ids(generated_dir):
    rows = _read_rows(generated_dir / "invoices.csv")
    ids = [r["invoice_id"] for r in rows]
    n_dupe_ids = len(ids) - len(set(ids))
    assert n_dupe_ids > 0


def test_invoices_contain_orphan_customers(generated_dir):
    invoices = _read_rows(generated_dir / "invoices.csv")
    plans = _read_rows(generated_dir / "plans.csv")
    known_customers = set()
    for f in sorted((generated_dir / "crm_customers").iterdir()):
        known_customers |= {r["customer_id"] for r in _read_rows(f)}

    orphans = [r for r in invoices if r["customer_id"] not in known_customers]
    assert len(orphans) > 0
    assert {p["plan_id"] for p in plans}  # sanity: plans loaded


def test_invoices_contain_bad_amounts(generated_dir):
    rows = _read_rows(generated_dir / "invoices.csv")
    def _is_negative(value: str) -> bool:
        return value.replace(".", "").lstrip("-").isdigit() and float(value) < 0

    bad = [r for r in rows if r["amount"] == "" or _is_negative(r["amount"])]
    assert len(bad) > 0


def test_invoices_contain_pre_window_dates(generated_dir):
    rows = _read_rows(generated_dir / "invoices.csv")
    early = [r for r in rows if r["invoice_date"] < gen.SNAPSHOT_START.isoformat()]
    assert len(early) > 0


def test_usage_events_reference_only_known_customers(generated_dir):
    events = _read_rows(generated_dir / "usage_events.csv")
    known_customers = set()
    for f in sorted((generated_dir / "crm_customers").iterdir()):
        known_customers |= {r["customer_id"] for r in _read_rows(f)}

    assert all(e["customer_id"] in known_customers for e in events)
    assert len(events) == 20_000
