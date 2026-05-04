-- HUB — Incremental — disable_hwm=True (no time filter, still deduplicates via NOT IN)

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
), distinct_target_hashkeys AS (
  SELECT
    HK_ORDER_H
  FROM "DV_DB"."RAW_VAULT"."HUB_ORDER"
), records_to_insert AS (
  SELECT
    *
  FROM earliest_hk_over_all_sources
  WHERE
    NOT HK_ORDER_H IN (SELECT
        HK_ORDER_H
    FROM distinct_target_hashkeys)
)
SELECT
  *
FROM records_to_insert
