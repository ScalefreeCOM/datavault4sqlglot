---
name: sync-dv-project
description: Syncs python_dv_project call sites after datavault4sqlglot or datavault4spark API changes. Use when the package API changed and project models need updating, or to check whether all sub-projects are in sync.
---

Sync `python_dv_project` with the current `datavault4sqlglot` (and optionally `datavault4spark`) API.

If the user passes `--check`, report mismatches only and make no changes (this is the default when no flag is given).
If the user passes `--fix`, apply all fixes and then verify by compiling.
If the user passes `--sub-project <name>`, restrict to that sub-project only: `sqlmesh`, `pure_python`, `bruin`, or `spark`.

## Sub-project overview

| Sub-project | Path | Execution method | Testable locally? |
|---|---|---|---|
| `pure_python` | `python_dv_project/pure_python/` | `python <file>.py` | Yes |
| `sqlmesh` | `python_dv_project/sqlmesh/models/` | `sqlmesh render <model>` | Yes |
| `bruin` | `python_dv_project/bruin/datavault/assets/` | Not runnable (needs Postgres) | No (indirect) |
| `spark` | `python_dv_project/spark/models/` | Not runnable (needs Databricks/JVM) | No (indirect) |

## Known models per sub-project

### pure_python
`stg_customers.py`, `stg_orders.py`, `customer_h.py`, `order_h.py`, `order_customer_l.py`,
`customer_0_s.py`, `customer_1_s.py`, `order_0_s.py`, `order_1_s.py`,
`customer_nh_s.py`, `order_nh_s.py`, `order_customer_nh_l.py`,
`order_status_r.py`, `order_status_rh.py`, `order_status_rs.py`,
`order_customer_0_es.py`, `customer_pit.py`, `order_bridge.py`

### sqlmesh (`dv.*` models)
`dv.customer_h`, `dv.order_h`, `dv.order_customer_l`,
`dv.customer_0_s`, `dv.order_0_s`,
`dv.customer_ns`, `dv.order_customer_nl`,
`dv.order_status_rh`, `dv.order_status_rs`,
`dv.order_customer_0_es`, `dv.customer_pit`, `dv.order_bridge`

### bruin (`dv.*` assets)
`dv.customer_0_s`, `dv.customer_1_s`, `dv.order_0_s`, `dv.order_1_s`,
`dv.customer_ns`, `dv.order_customer_nl`,
`dv.order_status_rh`, `dv.order_status_rs`,
`dv.order_customer_0_es`, `dv.customer_pit`, `dv.order_bridge`

### spark
`stg_customers.py`, `stg_orders.py`, `customer_h.py`, `order_h.py`, `order_customer_l.py`,
`customer_0_s.py`, `customer_1_s.py`, `order_0_s.py`, `order_1_s.py`,
`customer_nh_s.py`, `order_nh_s.py`, `order_customer_nh_l.py`,
`order_status_r.py`, `order_status_rh.py`, `order_status_rs.py`,
`order_customer_0_es.py`, `customer_pit.py`, `order_bridge.py`

## Efficiency notes

- **Parallelize Step 1**: send all package API reads in a single message — they are independent.
- **Grep before reading**: run all pattern greps first (parallel), then `Read` only files that matched. Don't read every file up front.
- **The glob path matters**: glob from `python_dv_project/` with `**/*.py`.
- **Config warnings are noise**: every run emits `WARNING:root:Configuration key 'default_unknown_rsrc'...` — not an error. Only flag: `Traceback`, `TypeError`, `ImportError`, `AttributeError`, `NameError`.
- **SQLMesh: use `render`, not `plan`**: `sqlmesh render <model>` compiles without a DB connection. Use the venv binary `C:\Users\mszerencse_scalefree\Documents\python_package\.venv\sqlglot\Scripts\sqlmesh.exe` with `--paths python_dv_project/sqlmesh` (note: `--paths`, not `--path`).
- **Bruin/Spark — validated indirectly**: these sub-projects are not locally runnable (need Postgres/Databricks). Validate by checking that imports compile (`python -c "import datavault4sqlglot; ..."`) and that pure_python/sqlmesh equivalents pass.
- **Commit fixes before any git merge**: uncommitted edits can be silently overwritten when `git merge` updates the working tree.
- **Pydantic v2 silently drops unknown fields**: `SourceModel(business_keys=[...])` constructs without error — the field is just ignored. Wrong SQL is the only symptom. Grep-based detection is the only reliable approach.

## Step 1 — Read the current package API (all in parallel)

Read these files from `C:\Users\mszerencse_scalefree\Documents\python_package\`:

- `datavault4sqlglot/datavault4sqlglot/metadata/source.py` — fields on `SourceModel`, `StageModel`, `SourceBinding`
- `datavault4sqlglot/datavault4sqlglot/generators/hub.py` — `HubGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/link.py` — `LinkGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/link_nh.py` — `LinkNHGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/satellite.py` — `SatelliteGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/satellite_v1.py` — `SatelliteV1Generator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/satellite_nh.py` — `SatelliteNHGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/ref_table.py` — `RefTableGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/ref_hub.py` — `RefHubGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/ref_sat.py` — `RefSatGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/effectivity_satellite.py` — `EffectivitySatelliteGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/generators/pit.py` — `PITGenerator.__init__` + `PitSatellite` dataclass
- `datavault4sqlglot/datavault4sqlglot/generators/bridge.py` — `BridgeGenerator.__init__` + `BridgeLink` dataclass
- `datavault4sqlglot/datavault4sqlglot/generators/stage.py` — `StageGenerator.__init__` signature
- `datavault4sqlglot/datavault4sqlglot/__init__.py` — top-level exports

If `datavault4spark/` exists, also read:
- `datavault4spark/datavault4spark/__init__.py` — spark top-level exports
- `datavault4spark/datavault4spark/generators/satellite_v1.py` — spark SatelliteV1 signature

## Step 2 — Grep for mismatches (all in parallel)

Run each grep across all `.py` files under `python_dv_project/`. Apply `--sub-project` filter if given.

| Grep pattern | What it flags |
|---|---|
| `business_keys=` | Should be on `SourceBinding`, not `SourceModel` |
| `foreign_hash_keys=` | Should be on `SourceBinding`, not `SourceModel` |
| `hash_key_col=` | Should be on `SourceBinding`, not `SourceModel` |
| `hashed_columns=` | Verify it's on `StageModel` not `SourceModel` |
| `source_models=\[` | Old plural param — Hub/Link use `sources=`, Satellite uses `source_model=` |
| `SatelliteV1Generator` | Check for `payload=` argument (removed) |
| `add_is_current=` | Old param name — EffSat uses `add_is_active=` |

For each match, read only that file to confirm context before deciding it's wrong.

Also check Bruin assets (`bruin/datavault/assets/**/*.py`) have `config.ldts_alias = "load_date"` and `config.rsrc_alias = "record_source"` — they have no `config.json`.

## Step 3 — Apply fixes (only when `--fix`)

Edit affected files. Then immediately commit:
```bash
git add <changed files>
git commit -m "sync: update call sites to current datavault4sqlglot API"
```

## Step 4 — Compile to verify

**pure_python** — run from `python_dv_project\pure_python\` using the venv Python:
```powershell
& "C:\Users\mszerencse_scalefree\Documents\python_package\.venv\sqlglot\Scripts\python.exe" <file>.py
```
Flag only: `Traceback|TypeError|ImportError|AttributeError|NameError`. Ignore config warnings.

**sqlmesh** — run from the repo root using `--paths`:
```powershell
& "C:\Users\mszerencse_scalefree\Documents\python_package\.venv\sqlglot\Scripts\sqlmesh.exe" --paths python_dv_project/sqlmesh render <model>
```
Models to render: `dv.customer_h`, `dv.order_h`, `dv.order_customer_l`, `dv.customer_0_s`, `dv.order_0_s`, `dv.customer_ns`, `dv.order_customer_nl`, `dv.order_status_rh`, `dv.order_status_rs`, `dv.order_customer_0_es`, `dv.customer_pit`, `dv.order_bridge`.

**bruin** — not runnable locally (needs Postgres). Validate by import-checking:
```powershell
& "C:\Users\mszerencse_scalefree\Documents\python_package\.venv\sqlglot\Scripts\python.exe" -c "
import sys, os
sys.path.insert(0, 'datavault4sqlglot')
from datavault4sqlglot.generators.satellite_nh import SatelliteNHGenerator
from datavault4sqlglot.generators.link_nh import LinkNHGenerator
from datavault4sqlglot.generators.ref_hub import RefHubGenerator
from datavault4sqlglot.generators.ref_sat import RefSatGenerator
from datavault4sqlglot.generators.effectivity_satellite import EffectivitySatelliteGenerator
from datavault4sqlglot.generators.pit import PITGenerator, PitSatellite
from datavault4sqlglot.generators.bridge import BridgeGenerator, BridgeLink
print('bruin imports OK')
"
```

**spark** — not runnable locally (needs JVM/Databricks). Validate by import-checking:
```powershell
& "C:\Users\mszerencse_scalefree\Documents\python_package\.venv\sqlglot\Scripts\python.exe" -c "
from datavault4spark import (SatelliteNHGenerator, LinkNHGenerator,
                              RefTableGenerator, RefHubGenerator, RefSatGenerator,
                              EffectivitySatelliteGenerator, PITGenerator, BridgeGenerator)
print('spark imports OK')
"
```

## Step 5 — Report

| File | Issue | Status |
|---|---|---|
| `pure_python/customer_h.py` | `business_keys` on `SourceModel` | Fixed / Needs fix |

In `--check` mode: list issues, no edits.
In `--fix` mode: show what changed, confirm compilation passed, confirm committed.
