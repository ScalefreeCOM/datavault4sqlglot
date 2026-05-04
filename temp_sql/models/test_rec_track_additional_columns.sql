-- REC-TRACK — Full Load — additional_columns=[BATCH_ID]

WITH src_new_0 AS (
  SELECT DISTINCT
    HK_ORDER_H AS HK_ORDER_H,
    LOAD_DATE AS ldts,
    CAST('ERP/ORDERS' AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('STG_ORDERS') AS VARCHAR(4000)) AS stg,
    BATCH_ID
  FROM "RAW_DB"."STAGE"."STG_ORDERS" AS src
), records_to_insert AS (
  SELECT
    HK_ORDER_H,
    ldts,
    rsrc,
    stg,
    BATCH_ID
  FROM src_new_0
  WHERE
    NOT ldts IN ('9999-12-31', '0001-01-01')
)
SELECT
  *
FROM records_to_insert
