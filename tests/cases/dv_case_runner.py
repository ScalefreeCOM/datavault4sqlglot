"""
Engine for the data-driven test cases: maps a Case onto a generator, seeds the
data, executes the generated SQL against DuckDB and compares the result.

The mechanics that every hand-written execution test repeats today
(seed → to_sql() → run_select() → compare) live here exactly once. Cases carry
only data + entity wiring (see ``case_schema``).

Important ordering / mapping notes:
- ``config`` is mutated only at *run* time (inside ``run_case``), never at
  import/collection time — the autouse ``reset_config`` fixture has already put
  the global config back to defaults before the test body runs.
- ``ldts`` / ``rsrc`` / ``ledts`` are placeholders in case data; they are
  resolved against the live ``config`` aliases *after* config overrides apply.
- ``SourceModel`` uses the pydantic alias ``schema``; ``bk_columns`` must stay
  ``None`` (not ``[]``) when unset or the generator's length check trips.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.generators.satellite_v1 import SatelliteV1Generator
from datavault4sqlglot.metadata import SourceBinding, SourceModel

from cases.case_schema import Case, Entity, MatchMode, SourceSpec, TableState

# Placeholders in case data → the config attribute that holds the real column name.
_ALIAS_PLACEHOLDERS = {
    "ldts": "ldts_alias",
    "rsrc": "rsrc_alias",
    "ledts": "ledts_alias",
}


def _resolve_alias(name: str) -> str:
    """Map a placeholder column name to its configured alias (live lookup)."""
    attr = _ALIAS_PLACEHOLDERS.get(name)
    return getattr(config, attr) if attr else name


def _resolve_row_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {_resolve_alias(k): v for k, v in row.items()}


# ---------------------------------------------------------------------------
# Case → generator
# ---------------------------------------------------------------------------

def _source_model(spec: SourceSpec) -> SourceModel:
    return SourceModel(
        database=spec.database,
        schema=spec.schema_name,  # pydantic alias
        table_name=spec.table,
        load_date_col=spec.load_date_col,
        record_source_col=spec.record_source_col,
    )


def _build_hub(case: Case) -> HubGenerator:
    es = case.entity_spec
    bindings = [
        SourceBinding(
            source=_source_model(s),
            bk_columns=s.bk_columns,          # None stays None on purpose
            rsrc_statics=s.rsrc_statics,
            additional_columns=s.additional_columns,
        )
        for s in (es.sources or [])
    ]
    return HubGenerator(
        target_table=es.target.table,
        target_schema=es.target.schema_name,
        target_database=es.target.database,
        sources=bindings,
        hashkey=es.hashkey,
        business_keys=es.business_keys,
        is_incremental=(case.mode.value == "incremental"),
        disable_hwm=bool(es.disable_hwm),
        additional_columns=es.additional_columns,
        dialect=case.dialect,
    )


def _build_link(case: Case) -> LinkGenerator:
    es = case.entity_spec
    bindings = [
        SourceBinding(
            source=_source_model(s),
            fk_columns=s.fk_columns,           # None stays None on purpose
            rsrc_statics=s.rsrc_statics,
            additional_columns=s.additional_columns,
        )
        for s in (es.sources or [])
    ]
    return LinkGenerator(
        target_table=es.target.table,
        target_schema=es.target.schema_name,
        target_database=es.target.database,
        sources=bindings,
        link_hash_key=es.link_hash_key,
        foreign_hash_keys=es.foreign_hash_keys,
        is_incremental=(case.mode.value == "incremental"),
        disable_hwm=bool(es.disable_hwm),
        additional_columns=es.additional_columns,
        dialect=case.dialect,
    )


def _build_satellite(case: Case) -> SatelliteGenerator:
    es = case.entity_spec
    return SatelliteGenerator(
        target_table=es.target.table,
        target_schema=es.target.schema_name,
        target_database=es.target.database,
        source_model=_source_model(es.source),
        parent_hash_key=es.parent_hash_key,
        hash_diff=es.hash_diff,
        payload=es.payload,                # None → generator uses []
        is_incremental=(case.mode.value == "incremental"),
        disable_hwm=bool(es.disable_hwm),
        source_is_single_batch=bool(es.source_is_single_batch),
        dialect=case.dialect,
    )


def _build_satellite_v1(case: Case) -> SatelliteV1Generator:
    es = case.entity_spec
    # sat_v1 is an end-dated view over an existing sat_v0 table; it has no
    # is_incremental / payload semantics — it always rebuilds from sat_v0.
    return SatelliteV1Generator(
        target_table=es.target.table,
        target_schema=es.target.schema_name,
        target_database=es.target.database,
        sat_v0_table=es.sat_v0.table,
        sat_v0_schema=es.sat_v0.schema_name,
        sat_v0_database=es.sat_v0.database,
        parent_hash_key=es.parent_hash_key,
        hash_diff=es.hash_diff,
        dialect=case.dialect,
    )


def build_generator(case: Case) -> BaseGenerator:
    """Dispatch a case to its generator. Hub + Link + Satellite (v0 + v1) are wired up."""
    if case.entity == Entity.hub:
        return _build_hub(case)
    if case.entity == Entity.link:
        return _build_link(case)
    if case.entity == Entity.satellite:
        return _build_satellite(case)
    if case.entity == Entity.satellite_v1:
        return _build_satellite_v1(case)
    raise NotImplementedError(
        f"entity '{case.entity.value}' is not yet supported by the runner"
    )


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def _seed_states(
    states: list[TableState],
    seed: Callable[[str, list[dict]], None],
    *,
    resolve_keys: bool,
) -> None:
    for state in states:
        rows = [_resolve_row_keys(r) for r in state.rows] if resolve_keys else state.rows
        seed(state.table, rows)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _project(rows: list[dict], keys: list[str]) -> list[tuple]:
    return [tuple(r.get(k) for k in keys) for r in rows]


def _diff_message(keys: list[str], expected: set, actual: set) -> str:
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    lines = [f"key_columns: {keys}"]
    if missing:
        lines.append(f"missing (expected, not in actual): {missing}")
    if unexpected:
        lines.append(f"unexpected (in actual, not expected): {unexpected}")
    return "\n".join(lines)


def _diff_message_exact(keys: list[str], expected: Counter, actual: Counter) -> str:
    """Multiset diff: report per-tuple count mismatches.

    `exact` cares about duplicate counts, so a plain set diff would hide a
    "expected this row twice, got it once" failure. List the counts instead.
    """
    lines = [f"key_columns: {keys}"]
    for tup in sorted(set(expected) | set(actual)):
        exp_n, act_n = expected.get(tup, 0), actual.get(tup, 0)
        if exp_n != act_n:
            lines.append(f"  {tup}: expected x{exp_n}, actual x{act_n}")
    return "\n".join(lines)


def _compare(actual: list[dict], expect) -> tuple[bool, str]:
    mode = expect.match_mode

    if mode == MatchMode.empty:
        ok = len(actual) == 0
        return ok, "" if ok else f"expected no rows, got {len(actual)}: {actual}"

    if mode == MatchMode.count:
        ok = len(actual) == expect.count
        return ok, "" if ok else f"expected {expect.count} rows, got {len(actual)}"

    expected_rows = [_resolve_row_keys(r) for r in (expect.rows or [])]
    if expect.key_columns is not None:
        keys = [_resolve_alias(k) for k in expect.key_columns]
    else:
        keys = list(expected_rows[0].keys()) if expected_rows else []

    # Guard: a key column present in neither the expected rows nor a non-empty actual
    # result would project to None on both sides and pass silently (a typo, or a column
    # the generator never emits). Fail loudly with the available columns instead.
    expected_cols = set().union(*(r.keys() for r in expected_rows)) if expected_rows else set()
    actual_cols = set().union(*(r.keys() for r in actual)) if actual else set()
    unknown = [k for k in keys if k not in expected_cols or (actual and k not in actual_cols)]
    if unknown:
        return False, (
            f"key_columns reference unknown column(s) {unknown}\n"
            f"expected columns: {sorted(expected_cols)}\n"
            f"actual columns:   {sorted(actual_cols)}"
        )

    actual_proj = _project(actual, keys)
    expected_proj = _project(expected_rows, keys)

    if mode == MatchMode.exact:
        expected_counter = Counter(expected_proj)
        actual_counter = Counter(actual_proj)
        ok = actual_counter == expected_counter
        msg = "" if ok else _diff_message_exact(keys, expected_counter, actual_counter)
        return ok, msg

    if mode == MatchMode.subset:
        ok = set(expected_proj) <= set(actual_proj)
    else:  # MatchMode.set
        ok = set(actual_proj) == set(expected_proj)

    msg = "" if ok else _diff_message(keys, set(expected_proj), set(actual_proj))
    return ok, msg


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_case(
    case: Case,
    *,
    seed: Callable[[str, list[dict]], None],
    run_select: Callable[[str], list[dict]],
    dump: Callable[..., None] | None = None,
) -> None:
    """
    Run one case end-to-end and assert its expectation.

    Raises AssertionError (with a readable row diff + the generated SQL) on
    mismatch, so pytest reports the failure at the calling test.
    """
    # 1. Apply config overrides (reset_config has already restored defaults).
    if case.config:
        config.update_from_dict(case.config)

    # 2. Seed: target (current_state) carries ldts/rsrc placeholders, the stage
    #    input carries physical column names — only the former gets resolved.
    _seed_states(case.current_state, seed, resolve_keys=True)
    _seed_states(case.input, seed, resolve_keys=False)

    # 3. Build generator + render SQL.
    sql = build_generator(case).to_sql()

    # 4. Execute.
    rows = run_select(sql)

    # 5. Compare.
    ok, message = _compare(rows, case.expect)
    if not ok:
        if dump is not None:
            dump(sql, label=f"{case.id} result")
        raise AssertionError(
            f"[case {case.id}] {case.title}\n{message}\n\n"
            f"--- generated SQL ---\n{sql}"
        )
