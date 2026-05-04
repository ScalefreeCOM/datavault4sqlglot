-- REC-TRACK -- Full Load — no rsrc_static (global dedup, no source filter)

WITH src_new_0 AS (
  SELECT DISTINCT
    HK_ORDER_H AS HK_ORDER_H,
    LOAD_DATE AS ldts,
    CAST(RECORD_SOURCE AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('STG_ORDERS') AS VARCHAR(4000)) AS stg
  FROM "RAW_DB"."STAGE"."STG_ORDERS" AS src
), records_to_insert AS (
  SELECT
    HK_ORDER_H,
    ldts,
    rsrc,
    stg
  FROM src_new_0
  WHERE
    NOT ldts IN ('9999-12-31', '0001-01-01')
)
SELECT
  *
FROM records_to_insert
