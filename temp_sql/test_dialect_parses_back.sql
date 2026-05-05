-- DIALECT -- sat_v1 @ duckdb

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order_h ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM "sat_order_details"
)
SELECT
  *,
  CASE WHEN ledts = '9999-12-31' THEN TRUE ELSE FALSE END AS "is_current"
FROM end_dated_source
