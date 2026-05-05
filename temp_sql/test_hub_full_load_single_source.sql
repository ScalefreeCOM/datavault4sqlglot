-- HUB -- Full Load — Single Source

WITH src_new_0 AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    ORDER_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDERS"
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM src_new_0
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_H ORDER BY ldts) = 1
)
SELECT
  *
FROM earliest_hk_over_all_sources
