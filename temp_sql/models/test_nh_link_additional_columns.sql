-- NH-LINK — Full Load — additional_columns=[BATCH_ID]

WITH src_new_0 AS (
  SELECT
    HK_ORDER_PRODUCT_L AS HK_ORDER_PRODUCT_L,
    HK_ORDER_H,
    HK_PRODUCT_H,
    QUANTITY,
    UNIT_PRICE,
    BATCH_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDER_PRODUCT"
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM src_new_0
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_PRODUCT_L ORDER BY ldts) = 1
)
SELECT
  *
FROM earliest_hk_over_all_sources
