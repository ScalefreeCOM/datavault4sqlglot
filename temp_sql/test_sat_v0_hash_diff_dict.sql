-- SAT v0 -- hash_diff as dict {source_column: RAW_HASHDIFF, alias: HD_ORDER_DETAILS}

WITH src_new AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    RAW_HASHDIFF AS HD_ORDER_DETAILS,
    ORDER_STATUS,
    TOTAL_PRICE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDERS"
), deduplicated_numbered_source AS (
  SELECT
    *
  FROM src_new
  QUALIFY
    CASE
      WHEN HD_ORDER_DETAILS = LAG(HD_ORDER_DETAILS) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
)
SELECT
  *
FROM deduplicated_numbered_source
