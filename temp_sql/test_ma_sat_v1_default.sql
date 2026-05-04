-- MA-SAT -- v1 — LEAD → ledts per (parent_hk, ma_attribute), is_current flag

WITH source_satellite AS (
  SELECT
    *
  FROM "DV_DB"."RAW_VAULT"."MA_SAT_CUSTOMER_PHONES"
), distinct_hk_ldts AS (
  SELECT DISTINCT
    HK_CUSTOMER_H,
    ldts
  FROM source_satellite
), end_dated_loads AS (
  SELECT
    HK_CUSTOMER_H,
    ldts,
    COALESCE(LEAD(ldts) OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM distinct_hk_ldts
), end_dated_source AS (
  SELECT
    src.HK_CUSTOMER_H AS HK_CUSTOMER_H,
    src.HD_CUSTOMER_PHONES AS HD_CUSTOMER_PHONES,
    src.rsrc AS rsrc,
    src.ldts AS ldts,
    edl.ledts AS ledts,
    CASE WHEN edl.ledts = '9999-12-31' THEN TRUE ELSE FALSE END AS "is_current",
    src.PHONE_TYPE AS PHONE_TYPE,
    src.PHONE_NUMBER AS PHONE_NUMBER,
    src.IS_PRIMARY AS IS_PRIMARY
  FROM source_satellite AS src
  LEFT JOIN end_dated_loads AS edl
    ON src.HK_CUSTOMER_H = edl.HK_CUSTOMER_H AND src.ldts = edl.ldts
)
SELECT
  *
FROM end_dated_source
