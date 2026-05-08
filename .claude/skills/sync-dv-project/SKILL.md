---
name: sync-dv-project
description: Syncs python_dv_project call sites after datavault4sqlglot or datavault4spark API changes. Use when the package API changed and project models need updating, or to check whether all sub-projects are in sync.
---

Sync `python_dv_project` with the current `datavault4sqlglot` (and optionally `datavault4spark`) API.

If the user passes `--check`, report mismatches only and make no changes (this is the default when no flag is given).
If the user passes `--fix`, apply all fixes and then verify by compiling.
If the user passes `--sub-project <name>`, restrict to that sub-project only: `sqlmesh`, `pure_python`, `bruin`, or `spark`.

## Step 1 — Read the current package API

Read these files from `C:\Users\mszerencse_scalefree\Documents\python_package\` to establish ground truth:

- `datavault4sqlglot/datavault4sqlglot/metadata/source.py` — fields on `SourceModel`, `StageModel`, `SourceBinding`
- `datavault4sqlglot/datavault4sqlglot/generators/hub.py` — `HubGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/link.py` — `LinkGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/satellite.py` — `SatelliteGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/satellite_v1.py` — `SatelliteV1Generator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/stage.py` — `StageGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/__init__.py` — top-level exports

If `datavault4spark/` exists at the same level, also read `datavault4spark/datavault4spark/generators/satellite_v1.py`.

## Step 2 — Scan call sites in python_dv_project

Glob all `.py` files under `python_dv_project/` (skip `__pycache__`). Apply the sub-project filter if given.

Check for these known mismatches:

| Pattern in file | Correct form |
|---|---|
| `SourceModel(..., business_keys=[...], ...)` | Move to `SourceBinding(source=..., business_keys=[...])` |
| `SourceModel(..., foreign_hash_keys=[...], ...)` | Move to `SourceBinding(source=..., foreign_hash_keys=[...])` |
| `SourceModel(..., hash_key_col=..., ...)` | Move to `SourceBinding(source=..., hash_key_col=...)` |
| `SourceModel(..., link_hash_key=..., ...)` | Remove — not a `SourceModel` field |
| `SourceModel(..., hashed_columns={...}, ...)` | Change to `StageModel` (stage generators only) |
| `source_models=[...]` as generator kwarg | Hub/Link: rename to `sources=[...]`; Satellite: rename to `source_model=...` singular |
| `SatelliteV1Generator(..., payload=[...], ...)` | Remove `payload` — unused by `SatelliteV1Generator` |
| `SourceBinding` needed but not imported | Add to import line |
| Bruin Python asset missing `config.ldts_alias` / `config.rsrc_alias` | Add both — Bruin has no `config.json` |

Also check whether any generator parameter names or accepted fields have changed by comparing the current `__init__` signatures against what the files actually pass.

## Step 3 — Compile to verify (only when --fix or when explicitly asked)

Run from `python_dv_project\pure_python\` using the project venv:
```
..\..\.venv\sqlglot\Scripts\python.exe <file>.py
```

For SQLMesh, run from `python_dv_project\sqlmesh\`:
```
..\..\.venv\sqlglot\Scripts\python.exe -m sqlmesh plan --no-prompts
```

Ignore Postgres connection errors in Bruin assets — only check that `_generator.to_sql()` executes without error.

## Step 4 — Report

Produce a table:

| File | Issue | Status |
|---|---|---|
| `pure_python/customer_h.py` | `business_keys` on `SourceModel` | Fixed / Needs fix |

In `--check` mode: list all issues, make no edits.
In `--fix` mode: show what was changed and confirm compilation passed.
