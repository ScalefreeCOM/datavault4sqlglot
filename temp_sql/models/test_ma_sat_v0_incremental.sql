-- MA-SAT — v0 — Incremental (global HWM, NOT EXISTS on parent_hk + hashdiff)

WITH src_new AS (
  SELECT
    HK_CUSTOMER_H AS HK_CUSTOMER_H,
    HD_CUSTOMER_PHONES AS HD_CUSTOMER_PHONES,
    PHONE_NUMBER,
    IS_PRIMARY,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_CUSTOMER_PHONES"
  WHERE
    LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '0001-01-01')
      FROM "DV_DB"."RAW_VAULT"."MA_SAT_CUSTOMER_PHONES"
      WHERE
        ldts <> '9999-12-31'
    )
), latest_entries_in_sat AS (
  SELECT
    HK_CUSTOMER_H,
    HD_CUSTOMER_PHONES
  FROM "DV_DB"."RAW_VAULT"."MA_SAT_CUSTOMER_PHONES"
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts DESC NULLS LAST) = 1
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
  WHERE
    NOT EXISTS(
      SELECT
        1
      FROM latest_entries_in_sat
      WHERE
        latest_entries_in_sat.HK_CUSTOMER_H = deduped_rows.HK_CUSTOMER_H
        AND latest_entries_in_sat.HD_CUSTOMER_PHONES = deduped_rows.HD_CUSTOMER_PHONES
    )
)
SELECT
  *
FROM records_to_insert
