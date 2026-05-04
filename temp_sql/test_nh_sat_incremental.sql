-- NH -- NH-Sat Incremental (NOT IN on parent_hk, existing keys skipped)

WITH source_data AS (
  SELECT
    HK_PRODUCT_H AS HK_PRODUCT_H,
    PRODUCT_NAME,
    CATEGORY,
    LIST_PRICE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_PRODUCT_DETAILS"
  WHERE
    LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '0001-01-01')
      FROM "DV_DB"."RAW_VAULT"."NH_SAT_PRODUCT_DETAILS"
      WHERE
        ldts <> '9999-12-31'
    )
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_PRODUCT_H ORDER BY ldts DESC NULLS LAST) = 1
), distinct_target_hashkeys AS (
  SELECT
    HK_PRODUCT_H
  FROM "DV_DB"."RAW_VAULT"."NH_SAT_PRODUCT_DETAILS"
), records_to_insert AS (
  SELECT
    *
  FROM source_data
  WHERE
    NOT HK_PRODUCT_H IN (SELECT
        HK_PRODUCT_H
    FROM distinct_target_hashkeys)
)
SELECT
  *
FROM records_to_insert
