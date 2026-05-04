-- HUB -- Full Load — Multi Source (UNION ALL)

WITH src_new_0 AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    ORDER_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDERS"
), src_new_1 AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    WEB_ORDER_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_WEB_ORDERS"
), source_new_union AS (
  SELECT
    *
  FROM src_new_0
  UNION ALL
  SELECT
    *
  FROM src_new_1
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM source_new_union
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_H ORDER BY ldts) = 1
)
SELECT
  *
FROM earliest_hk_over_all_sources
