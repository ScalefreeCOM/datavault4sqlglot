# datavault4sqlglot + datavault4spark — Development Plan

Date: 2026-05-08

## Approach

Each entity type is implemented in both packages in parallel (sqlglot AST generator +
PySpark DataFrame generator). After each type: compile check + sync python_dv_project
sample models + tests. Multi-Active Satellite is deprioritized indefinitely.

## Step-by-step order

### Step 1 — Non-Historized Satellite (NH Sat)
- No hash diff, no LAG dedup, no history preserved
- Deduplicates to **latest** record per parent_hk (ROW_NUMBER DESC)
- Output designed for MERGE/upsert materialization (not append)
- Optional global HWM filter (same as sat_v0)
- Metadata: reuses SourceModel, no new fields needed

### Step 2 — Non-Historized Link (NH Link)
- Same pattern as NH Sat but for link entities
- Requires ≥2 foreign_hash_keys
- Deduplicates to latest per link_hk
- Output designed for MERGE/upsert

### Step 3 — Reference Table
- Simplest generator: full-load SELECT with optional column aliasing
- Optional single hash key on business key column(s)
- No incremental logic — always full overwrite
- Metadata: may reuse StageModel or new RefModel

### Step 4 — Effectivity Satellite
- Tracks when a link relationship is active or closed
- Two patterns:
  - **Open**: record appears in source for the first time → insert with ldts, ledts = end_of_all_times
  - **Close**: record disappears from a full extract → update ledts to current ldts
- Requires full-extract assumption for close detection
- Most complex of the remaining generators

### Step 5 — PIT + Bridge tables
- **PIT**: for each snapshot date × parent_hk, take MAX(ldts) from each satellite
  - Snapshot grain is configurable (daily/hourly)
- **Bridge**: joins PIT snapshot to link hash keys
- These are query helpers (read-only derived layers), not raw vault loaders
- Implement as a pair since Bridge depends on PIT

## Out of scope (for now)
- Multi-Active Satellites — complex, deprioritized
