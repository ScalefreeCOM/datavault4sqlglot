# Data-driven test cases

Each `*.yml` file under this directory is **one execution test**, defined as data
instead of Python. A runner seeds the data into in-memory DuckDB, runs the
generated SQL, and compares the result against the expectation.

- Schema + validation: [`case_schema.py`](case_schema.py)
- Engine (case → generator → seed → run → compare): [`dv_case_runner.py`](dv_case_runner.py)
- Discovery: [`case_loader.py`](case_loader.py)
- pytest adapter: [`../test_execution_cases.py`](../test_execution_cases.py)

Run them:

```bash
python -m pytest tests/test_execution_cases.py -v
# a single case (the spec id is the pytest id):
python -m pytest "tests/test_execution_cases.py::test_execution_case[2.2.2.3]"
```

> Status: **Hub + Link + Satellite (v0 + v1) wired** — **48 cases** (Hub 11, Link 10,
> Satellite-v0 24, Satellite-v1 3). Hub/Link/Sat-v0 are a 1:1 port of the
> hand-written `test_execution_{hub,link,satellite}.py`; `satellite_v1` is wired
> into the runner (`entity_spec.sat_v0`) and has row-level execution cases (it
> previously only had AST/string tests). The hand-written `tests/test_execution_*.py`
> are **kept** as a differential oracle; removing them is a separate later cleanup.
>
> **Coverage gate:** [`../spec_manifest.yml`](../spec_manifest.yml) lists the spec-IDs
> a case must exist for, and [`../test_spec_coverage.py`](../test_spec_coverage.py)
> fails on any drift. Two hub cases (`2.2.1.3`, `2.2.2.4`) are listed under
> `partial_coverage`: they assert the deterministic single-row dedup but **not** the
> spec's "leading source wins" tie-break, because the generator's dedup has no
> secondary ordering key (a documented generator gap, not a test gap).

## Anatomy of a case

A case separates the three things a hand-written test mixes together:

- **Data** (varies per case, comes from the Excel spec) → `current_state`, `input`, `expect`
- **Entity config** (how the generator is wired) → `entity_spec`, `mode`
- **Mechanics** (seed → run → compare) → lives once in the runner, not in the case

```yaml
id: "2.2.2.3"                 # spec id — becomes the pytest id
title: "..."                  # human-readable description
entity: hub                   # hub | link | satellite | satellite_v1
mode: incremental             # initial | incremental  (→ is_incremental)
# dialect: duckdb             # optional, defaults to duckdb (the test engine)
# config: { ldts_alias: ... } # optional DataVaultConfig overrides

entity_spec:                  # how to wire the generator (Hub shown)
  target: { database: DV, schema: RAW_VAULT, table: HUB_ORDER }
  hashkey: HK_ORDER_H
  business_keys: [ORDER_ID]
  sources:
    - { database: RAW_DB, schema: STAGE, table: STG_SAP_ORDERS,
        load_date_col: LOAD_DATE, record_source_col: RECORD_SOURCE,
        bk_columns: [SAP_ORDER_ID] }   # omit when the source already uses ORDER_ID

current_state:                # target table BEFORE the load (incremental only)
  - table: DV.RAW_VAULT.HUB_ORDER
    rows:
      - { HK_ORDER_H: "h_existing", ORDER_ID: "EXIST", ldts: "2026-01-01", rsrc: "SAP/ORDERS" }

input:                        # staging table(s) — the incoming batch
  - table: RAW_DB.STAGE.STG_SAP_ORDERS
    rows:
      - { HK_ORDER_H: "h_new", SAP_ORDER_ID: "NEW", LOAD_DATE: "2026-01-05", RECORD_SOURCE: "SAP/ORDERS" }

expect:                       # the assertion
  match_mode: set
  key_columns: [HK_ORDER_H, ldts, rsrc]
  rows:
    - { HK_ORDER_H: "h_new", ldts: "2026-01-03", rsrc: "WEB/ORDERS" }
```

## Conventions & gotchas

- **Quote scalar values** (`"h1"`, `"2026-01-03"`), especially dates — otherwise
  YAML parses `2026-01-03` as a date object instead of the string DuckDB stores.
- **`ldts` / `rsrc` / `ledts` are placeholders.** Use them literally in
  `current_state` rows and in `expect`; the runner resolves them to the configured
  aliases (`config.ldts_alias`, …) at run time. Staging `input` rows use the
  *physical* column names instead (`LOAD_DATE`, `RECORD_SOURCE`).
- **Hash keys / hash diffs are plain seeded strings** (`h1`, `h_new`). The
  Hub/Link/Sat generators read them as opaque columns — they do not compute
  hashes — so there is no hash to reproduce in `expect`.
- **`bk_columns` / `fk_columns`: omit when unused.** An empty list trips the
  generator's length check; leave them out so they default to `None`.

## `match_mode` reference

| mode | needs | meaning |
|---|---|---|
| `set` (default) | `rows`, `key_columns` | result projected onto `key_columns`, compared as a set (order/dup independent) |
| `exact` | `rows`, `key_columns` | as `set`, but counts matter (multiset) |
| `subset` | `rows`, `key_columns` | expected rows must be a subset of the result |
| `count` | `count` | only the number of result rows |
| `empty` | – | the result must be empty |

## Adding a case

1. Create `tests/cases/<entity>/<id_with_underscores>.yml` (e.g. `hub/2_1_2_2.yml`).
2. Fill in `entity_spec` + `input` (+ `current_state` for incremental) + `expect`.
3. `python -m pytest "tests/test_execution_cases.py::test_execution_case[<id>]" -v`.

A malformed file fails loudly at collection time (no silent skips).
