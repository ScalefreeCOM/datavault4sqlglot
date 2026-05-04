-- NH -- NH-Link Incremental — Single Source, no rsrc_static (global HWM + NOT IN)

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
  WHERE
    LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '0001-01-01')
      FROM "DV_DB"."RAW_VAULT"."NH_LNK_ORDER_PRODUCT"
      WHERE
        ldts <> '9999-12-31'
    )
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM src_new_0
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_PRODUCT_L ORDER BY ldts) = 1
), distinct_target_hashkeys AS (
  SELECT
    HK_ORDER_PRODUCT_L
  FROM "DV_DB"."RAW_VAULT"."NH_LNK_ORDER_PRODUCT"
), records_to_insert AS (
  SELECT
    *
  FROM earliest_hk_over_all_sources
  WHERE
    NOT HK_ORDER_PRODUCT_L IN (SELECT
        HK_ORDER_PRODUCT_L
    FROM distinct_target_hashkeys)
)
SELECT
  *
FROM records_to_insert
