-- MA-SAT -- v0 — additional_columns=[PHONE_TYPE, BATCH_ID]

WITH src_new AS (
  SELECT
    HK_CUSTOMER_H AS HK_CUSTOMER_H,
    HD_CUSTOMER_PHONES AS HD_CUSTOMER_PHONES,
    PHONE_NUMBER,
    IS_PRIMARY,
    PHONE_TYPE,
    BATCH_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_CUSTOMER_PHONES"
), deduped_row_hashdiff AS (
  SELECT
    HK_CUSTOMER_H,
    ldts,
    HD_CUSTOMER_PHONES
  FROM src_new
  QUALIFY
    CASE
      WHEN HD_CUSTOMER_PHONES = LAG(HD_CUSTOMER_PHONES) OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
), deduped_rows AS (
  SELECT
    sd.HK_CUSTOMER_H AS HK_CUSTOMER_H,
    sd.HD_CUSTOMER_PHONES AS HD_CUSTOMER_PHONES,
    sd.PHONE_NUMBER AS PHONE_NUMBER,
    sd.IS_PRIMARY AS IS_PRIMARY,
    sd.PHONE_TYPE AS PHONE_TYPE,
    sd.BATCH_ID AS BATCH_ID,
    sd.ldts AS ldts,
    sd.rsrc AS rsrc
  FROM src_new AS sd
  INNER JOIN deduped_row_hashdiff AS drh
    ON sd.HK_CUSTOMER_H = drh.HK_CUSTOMER_H
    AND sd.ldts = drh.ldts
    AND sd.HD_CUSTOMER_PHONES = drh.HD_CUSTOMER_PHONES
), records_to_insert AS (
  SELECT
    *
  FROM deduped_rows
)
SELECT
  *
FROM records_to_insert
