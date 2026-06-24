# datavault4sqlglot — Execution Testing Framework

A data-driven test framework that executes each generator's SQL against an in-memory
DuckDB and asserts on the resulting rows. A *case* is a YAML file carrying input data,
the expected output and the generator wiring; the mechanics (seed → `to_sql()` → run →
compare) live once in the runner, so a new case only adds data.

## Layout

- `tests/cases/case_schema.py` — pydantic schema + per-entity validation
- `tests/cases/case_loader.py` — discovery/validation of `tests/cases/**/*.yml`
- `tests/cases/dv_case_runner.py` — the engine (dispatch → seed → run → compare)
- `tests/cases/<entity>/*.yml` — the cases
- `tests/test_execution_cases.py` — one parametrized test per case (pytest id = spec id)
- `tests/spec_manifest.yml` + `tests/test_spec_coverage.py` — the coverage gate
- `tests/test_runner_internals.py` — unit tests for the comparison logic

## Coverage (48 cases)

| Entity | Cases | Source of the spec IDs |
|---|---|---|
| hub | 11 | Excel `TestCases` sheet |
| link | 10 | hand-written Python oracle (the Excel has no link cases) |
| satellite v0 | 24 | Excel `TestCases` sheet |
| satellite v1 | 3 | derived from the datavault4dbt `sat_v1` macro semantics |

The coverage gate enforces, per entity, that every manifest spec-ID has exactly one
case (and vice-versa), so missing/orphan/misfiled cases fail loudly. Two hub IDs
(`2.2.1.3`, `2.2.2.4`) are listed under `partial_coverage` — see Known limitations.

## Scope

- **In scope:** the execution behaviour of the loading generators — Hub, Link,
  Satellite v0 and v1. The hand-written `test_execution_*.py` are kept as an
  independent differential cross-check.
- **Out of scope** (covered by other, existing tests): structural/AST checks, dialect
  transpilation, configuration, hashing, and the **Stage** generator (which computes
  hashes — a different mechanism).

## Comparison modes

`exact` (default, multiset), `set`, `subset`, `count`, `empty` — projected onto
`key_columns`. On failure the runner reports the differing rows (count-aware for
`exact`). A key column that exists in neither the expected rows nor the actual result
fails loudly rather than passing silently.

## Known limitations

- **Hub same-LDTS tie-break:** the multi-source dedup orders only by `ldts` with no
  secondary key, so on equal `ldts` across sources the surviving record source is not
  deterministically defined. Cases `2.2.1.3` / `2.2.2.4` therefore assert only the
  deterministic single-row dedup (`partial_coverage`).
- **All-VARCHAR seeding:** values and row sets are verified; column data *types* are not.
- Two `xfailed` tests in `tests/test_edge_cases.py` document pre-existing generator
  limitations (Hub does not validate a non-empty business-key list; Stage can emit
  `SELECT FROM <table>`); they are unrelated to this framework.

## Run

```bash
python -m pip install -e ".[test]"
python -m pytest -q                                   # full suite
python -m pytest tests/test_execution_cases.py -v     # framework only (48 cases)
python -m pytest tests/test_spec_coverage.py -v       # coverage gate
python -m pytest "tests/test_execution_cases.py::test_execution_case[2.2.2.3]"   # one case
```
