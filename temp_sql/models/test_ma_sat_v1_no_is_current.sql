-- MA-SAT — v1 — add_is_current=False (only ledts, no flag)

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
    COALESCE(LEAD(ldts) OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM distinct_hk_ldts
), end_dated_source AS (
  SELECT
    src.HK_CUSTOMER_H AS HK_CUSTOMER_H,
    src.HD_CUSTOMER_PHONES AS HD_CUSTOMER_PHONES,
    src.rsrc AS rsrc,
    src.ldts AS ldts,
    edl.ledts AS ledts,
    src.PHONE_TYPE AS PHONE_TYPE
  FROM source_satellite AS src
  LEFT JOIN end_dated_loads AS edl
    ON src.HK_CUSTOMER_H = edl.HK_CUSTOMER_H AND src.ldts = edl.ldts
)
SELECT
  *
FROM end_dated_source
