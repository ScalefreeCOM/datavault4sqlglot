-- MA-SAT -- v0 — hash_diff as dict {source_column: raw_hd, alias: hashdiff}

WITH src_new AS (
  SELECT
    hk_order AS hk_order,
    raw_hd AS hashdiff,
    phone,
    ldts AS ldts,
    rsrc AS rsrc
  FROM "stg_orders"
), deduped_row_hashdiff AS (
  SELECT
    hk_order,
    ldts,
    hashdiff
  FROM src_new
  QUALIFY
    CASE
      WHEN hashdiff = LAG(hashdiff) OVER (PARTITION BY hk_order ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
), deduped_rows AS (
  SELECT
    sd.hk_order AS hk_order,
    sd.hashdiff AS hashdiff,
    sd.phone AS phone,
    sd.ldts AS ldts,
    sd.rsrc AS rsrc
  FROM src_new AS sd
  INNER JOIN deduped_row_hashdiff AS drh
    ON sd.hk_order = drh.hk_order AND sd.ldts = drh.ldts AND sd.hashdiff = drh.hashdiff
), records_to_insert AS (
  SELECT
    *
  FROM deduped_rows
)
SELECT
  *
FROM records_to_insert
