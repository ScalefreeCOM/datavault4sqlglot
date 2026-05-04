-- REC-TRACK — Incremental — no rsrc_static, single source (global HWM)

WITH distinct_concated_target AS (
  SELECT
    CONCAT(CAST(HK_ORDER_H AS VARCHAR(4000)), ldts, rsrc) AS concat
  FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
), src_new_0 AS (
  SELECT DISTINCT
    HK_ORDER_H AS HK_ORDER_H,
    LOAD_DATE AS ldts,
    CAST(RECORD_SOURCE AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('STG_ORDERS') AS VARCHAR(4000)) AS stg
  FROM "RAW_DB"."STAGE"."STG_ORDERS" AS src
  WHERE
    src.LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '0001-01-01')
      FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
      WHERE
        ldts <> '9999-12-31'
    )
), records_to_insert AS (
  SELECT
    HK_ORDER_H,
    ldts,
    rsrc,
    stg
  FROM src_new_0
  WHERE
    NOT ldts IN ('9999-12-31', '0001-01-01')
    AND NOT CONCAT(CAST(HK_ORDER_H AS VARCHAR(4000)), ldts, rsrc) IN (SELECT
        concat
    FROM distinct_concated_target)
)
SELECT
  *
FROM records_to_insert
