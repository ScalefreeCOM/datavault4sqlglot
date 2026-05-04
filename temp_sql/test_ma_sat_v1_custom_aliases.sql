-- MA-SAT -- v1 — ledts_alias=LOAD_END_DATE, is_current_col=IS_LATEST

WITH source_satellite AS (
  SELECT
    *
  FROM "MA_SAT_CUSTOMER_PHONES"
), distinct_hk_ldts AS (
  SELECT DISTINCT
    HK_CUSTOMER_H,
    ldts
  FROM source_satellite
), end_dated_loads AS (
  SELECT
    HK_CUSTOMER_H,
    ldts,
    COALESCE(LEAD(ldts) OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts), '9999-12-31') AS "LOAD_END_DATE"
  FROM distinct_hk_ldts
), end_dated_source AS (
  SELECT
    src.HK_CUSTOMER_H AS HK_CUSTOMER_H,
    src.HD_CUSTOMER_PHONES AS HD_CUSTOMER_PHONES,
    src.rsrc AS rsrc,
    src.ldts AS ldts,
    edl.LOAD_END_DATE AS LOAD_END_DATE,
    CASE WHEN edl.LOAD_END_DATE = '9999-12-31' THEN TRUE ELSE FALSE END AS "IS_LATEST",
    src.PHONE_TYPE AS PHONE_TYPE
  FROM source_satellite AS src
  LEFT JOIN end_dated_loads AS edl
    ON src.HK_CUSTOMER_H = edl.HK_CUSTOMER_H AND src.ldts = edl.ldts
)
SELECT
  *
FROM end_dated_source
