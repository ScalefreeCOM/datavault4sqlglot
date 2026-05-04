-- SAT v1 -- custom end_of_all_times=2099-12-31 in COALESCE + is_current CASE

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '2099-12-31') AS "ledts"
  FROM "sat_orders"
)
SELECT
  *,
  CASE WHEN ledts = '2099-12-31' THEN TRUE ELSE FALSE END AS "is_current"
FROM end_dated_source
