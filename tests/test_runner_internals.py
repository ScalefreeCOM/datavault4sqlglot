"""
Unit tests for the case runner's internal comparison logic and the expectation
schema (no DuckDB needed).

The ``_compare`` tests exercise the comparator directly, so we can assert on the
*quality* of the failure message — not just pass/fail. The ``ExpectSpec`` tests
pin down which malformed expectations the schema rejects loudly.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cases.case_schema import ExpectSpec, MatchMode
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


# ---------------------------------------------------------------------------
# ExpectSpec schema validation — reject degenerate expectations loudly
# ---------------------------------------------------------------------------

def test_empty_key_columns_rejected():
    # [] projects every row onto the empty tuple (), so any non-empty result
    # would match any other — a silent always-pass. Must be rejected.
    with pytest.raises(ValidationError):
        ExpectSpec(match_mode="set", key_columns=[], rows=[{"k": "a"}])


def test_subset_with_empty_rows_rejected():
    # An empty expected subset is a subset of *every* result, so it asserts
    # nothing. Use match_mode 'empty' to assert no rows instead.
    with pytest.raises(ValidationError):
        ExpectSpec(match_mode="subset", key_columns=["k"], rows=[])


def test_negative_count_rejected():
    # A row count can never be negative; reject it rather than compare against
    # an impossible value.
    with pytest.raises(ValidationError):
        ExpectSpec(match_mode="count", count=-1)


def test_default_match_mode_is_exact():
    # The default is the strict, count-aware mode; `set` must be opted into so a
    # case that forgets to specify still rejects duplicate/missing result rows.
    assert ExpectSpec(key_columns=["k"], rows=[{"k": "a"}]).match_mode == MatchMode.exact


# ---------------------------------------------------------------------------
# match_mode semantics — one test per mode, both directions where it matters
# ---------------------------------------------------------------------------

def test_set_ignores_duplicate_rows_on_purpose():
    # `set` is the deliberately duplicate-insensitive mode: a row coming back
    # twice still matches a single expected row. This is WHY row-exact cases use
    # `exact` instead — documented here so the behaviour can't drift unnoticed.
    expect = ExpectSpec(match_mode="set", key_columns=["k"], rows=[{"k": "a"}])
    ok, _ = _compare([{"k": "a"}, {"k": "a"}], expect)
    assert ok is True


def test_set_fails_on_differing_rows():
    # The complement of the duplicate-insensitivity test: `set` must still reject a
    # result whose row set differs from the expectation, otherwise it would always
    # pass. Reports both the missing and the unexpected row.
    expect = ExpectSpec(match_mode="set", key_columns=["k"], rows=[{"k": "a"}])
    ok, msg = _compare([{"k": "b"}], expect)
    assert ok is False
    assert "a" in msg and "b" in msg


def test_exact_rejects_unexpected_duplicate():
    # The other direction from test_exact_diff_reports_duplicate_count_mismatch:
    # expecting a row once but getting it twice must fail under `exact`.
    expect = ExpectSpec(match_mode="exact", key_columns=["k"], rows=[{"k": "a"}])
    ok, msg = _compare([{"k": "a"}, {"k": "a"}], expect)
    assert ok is False
    assert "x1" in msg and "x2" in msg  # "expected x1, actual x2"


def test_subset_passes_when_expected_is_subset():
    expect = ExpectSpec(match_mode="subset", key_columns=["k"], rows=[{"k": "a"}])
    ok, _ = _compare([{"k": "a"}, {"k": "b"}], expect)
    assert ok is True


def test_subset_fails_when_expected_row_missing():
    expect = ExpectSpec(match_mode="subset", key_columns=["k"], rows=[{"k": "c"}])
    ok, msg = _compare([{"k": "a"}, {"k": "b"}], expect)
    assert ok is False
    assert "c" in msg


def test_count_matches_row_count():
    expect = ExpectSpec(match_mode="count", count=2)
    ok, _ = _compare([{"k": "a"}, {"k": "b"}], expect)
    assert ok is True


def test_count_mismatch_fails():
    expect = ExpectSpec(match_mode="count", count=3)
    ok, msg = _compare([{"k": "a"}, {"k": "b"}], expect)
    assert ok is False
    assert "3" in msg and "2" in msg


def test_empty_passes_on_no_rows():
    expect = ExpectSpec(match_mode="empty")
    ok, _ = _compare([], expect)
    assert ok is True


def test_empty_fails_when_rows_present():
    expect = ExpectSpec(match_mode="empty")
    ok, msg = _compare([{"k": "a"}], expect)
    assert ok is False
    assert "1" in msg
