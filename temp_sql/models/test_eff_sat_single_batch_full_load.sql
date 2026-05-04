-- EFF-SAT — Single-Batch Full Load (new_hashkeys, every key → is_active=1)

WITH source_data AS (
  SELECT
    HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDER_CUSTOMER" AS src
  WHERE
    NOT LOAD_DATE IN ('0001-01-01', '9999-12-31')
), new_hashkeys AS (
  SELECT DISTINCT
    src.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    src.ldts AS ldts,
    src.rsrc AS rsrc,
    1 AS is_active
  FROM source_data AS src
), records_to_insert AS (
  SELECT
    *
  FROM new_hashkeys
)
SELECT
  ri.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
  ri.ldts AS ldts,
  ri.rsrc AS rsrc,
  CAST(ri.is_active AS BOOLEAN) AS "is_active"
FROM records_to_insert AS ri
