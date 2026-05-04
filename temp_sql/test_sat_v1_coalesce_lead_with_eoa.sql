-- SAT v1 -- COALESCE wraps LEAD result with end_of_all_times=9999-12-31

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM "sat_orders"
)
SELECT
  *,
  CASE WHEN ledts = '9999-12-31' THEN TRUE ELSE FALSE END AS "is_current"
FROM end_dated_source
