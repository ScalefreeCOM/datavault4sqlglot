-- SAT v1 -- add_is_current=False (only ledts, no flag)

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM "sat_orders"
)
SELECT
  *
FROM end_dated_source
