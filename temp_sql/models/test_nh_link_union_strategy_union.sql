-- NH-LINK — Full Load — Multi Source, union_strategy=UNION (DISTINCT across sources)

WITH src_new_0 AS (
  SELECT
    HK_ORDER_PRODUCT_L AS HK_ORDER_PRODUCT_L,
    HK_ORDER_H,
    HK_PRODUCT_H,
    QUANTITY,
    UNIT_PRICE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDER_PRODUCT"
), src_new_1 AS (
  SELECT
    HK_ORDER_PRODUCT_L AS HK_ORDER_PRODUCT_L,
    HK_ORDER_H,
    HK_PRODUCT_H,
    QUANTITY,
    UNIT_PRICE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_WEB_ORDER_PRODUCT"
), source_new_union AS (
  SELECT
    *
  FROM src_new_0
  UNION
  SELECT
    *
  FROM src_new_1
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM source_new_union
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_PRODUCT_L ORDER BY ldts) = 1
)
SELECT
  *
FROM earliest_hk_over_all_sources
