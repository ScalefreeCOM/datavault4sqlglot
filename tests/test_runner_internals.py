"""
Unit tests for the case runner's internal comparison logic (no DuckDB needed).

These exercise `_compare` directly, so we can assert on the *quality* of the
failure message — not just pass/fail.
"""
from __future__ import annotations

from cases.case_schema import ExpectSpec
from cases.dv_case_runner import _compare


def test_exact_diff_reports_duplicate_count_mismatch():
    # 'exact' compares as a multiset: expecting "a" twice but getting it once is a
    # failure even though the *set* of rows is identical. The diff must surface the
    # count discrepancy, otherwise a set-based diff would show nothing useful.
    expect = ExpectSpec(match_mode="exact", key_columns=["k"], rows=[{"k": "a"}, {"k": "a"}])
    actual = [{"k": "a"}]  # one occurrence instead of two

    ok, msg = _compare(actual, expect)

    assert ok is False
    assert "x2" in msg and "x1" in msg  # "expected x2, actual x1"
    assert "('a',)" in msg


def test_unknown_key_column_fails_loudly():
    # A key column that exists in neither the expected rows nor the actual result
    # would otherwise project to None on both sides and pass silently (a typo, or a
    # column the generator never emits). It must fail with a clear message instead.
    expect = ExpectSpec(match_mode="set", key_columns=["k", "NOPE"], rows=[{"k": "a"}])
    actual = [{"k": "a"}]  # no "NOPE" column anywhere

    ok, msg = _compare(actual, expect)

    assert ok is False
    assert "NOPE" in msg
