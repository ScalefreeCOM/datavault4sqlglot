-- REC-TRACK -- Incremental — rsrc_static=ERP/ORDERS (per-source HWM + CONCAT dedup)

WITH distinct_concated_target AS (
  SELECT
    CONCAT(CAST(HK_ORDER_H AS VARCHAR(4000)), ldts, rsrc) AS concat
  FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
), max_ldts_per_rsrc_static_in_target AS (
  SELECT
    MAX(ldts) AS max_ldts,
    'ERP/ORDERS' AS rsrc_static
  FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
  WHERE
    rsrc LIKE 'ERP/ORDERS' AND ldts <> '9999-12-31'
), src_new_0 AS (
  SELECT DISTINCT
    HK_ORDER_H AS HK_ORDER_H,
    LOAD_DATE AS ldts,
    CAST('ERP/ORDERS' AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('STG_ORDERS') AS VARCHAR(4000)) AS stg
  FROM "RAW_DB"."STAGE"."STG_ORDERS" AS src
  LEFT JOIN max_ldts_per_rsrc_static_in_target AS max
    ON max.rsrc_static LIKE 'ERP/ORDERS'
  WHERE
    src.LOAD_DATE > COALESCE(max.max_ldts, '0001-01-01')
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
