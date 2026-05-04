-- SAT — sat_v0 — additional_columns=[BATCH_ID]

WITH src_new AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    HK_ORDER_DETAILS_D AS HK_ORDER_DETAILS_D,
    ORDER_STATUS,
    TOTAL_PRICE,
    ORDER_DATE,
    BATCH_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDERS"
), deduplicated_numbered_source AS (
  SELECT
    *
  FROM src_new
  QUALIFY
    CASE
      WHEN HK_ORDER_DETAILS_D = LAG(HK_ORDER_DETAILS_D) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
)
SELECT
  *
FROM deduplicated_numbered_source
