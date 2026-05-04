-- NH-SAT — Full Load, Single-Batch (no QUALIFY, source is one snapshot)

WITH source_data AS (
  SELECT
    HK_PRODUCT_H AS HK_PRODUCT_H,
    PRODUCT_NAME,
    CATEGORY,
    LIST_PRICE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_PRODUCT_DETAILS"
)
SELECT
  *
FROM source_data
