-- LINK -- Incremental — Multi Source, no rsrc_static (no HWM, only NOT IN dedup)

WITH src_new_0 AS (
  SELECT
    HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    HK_ORDER_H,
    HK_CUSTOMER_H,
    ldts AS ldts,
    rsrc AS rsrc
  FROM "STG_A"
), src_new_1 AS (
  SELECT
    HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    HK_ORDER_H,
    HK_CUSTOMER_H,
    ldts AS ldts,
    rsrc AS rsrc
  FROM "STG_B"
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
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_CUSTOMER_L ORDER BY ldts) = 1
), distinct_target_hashkeys AS (
  SELECT
    HK_ORDER_CUSTOMER_L
  FROM "DV_DB"."RAW_VAULT"."LNK_ORDER_CUSTOMER"
), records_to_insert AS (
  SELECT
    *
  FROM earliest_hk_over_all_sources
  WHERE
    NOT HK_ORDER_CUSTOMER_L IN (SELECT
        HK_ORDER_CUSTOMER_L
    FROM distinct_target_hashkeys)
)
SELECT
  *
FROM records_to_insert
