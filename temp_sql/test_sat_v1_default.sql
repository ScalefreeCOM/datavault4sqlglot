-- SAT v1 -- Default — LEAD window for ledts, is_current flag

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM "DV_DB"."RAW_VAULT"."SAT_ORDER_DETAILS"
)
SELECT
  *,
  CASE WHEN ledts = '9999-12-31' THEN TRUE ELSE FALSE END AS "is_current"
FROM end_dated_source
