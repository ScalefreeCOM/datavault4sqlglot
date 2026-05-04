-- SAT v1 -- config.ledts_alias=end_date used when ledts_alias not set explicitly

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '9999-12-31') AS "end_date"
  FROM "sat_orders"
)
SELECT
  *,
  CASE WHEN end_date = '9999-12-31' THEN TRUE ELSE FALSE END AS "is_current"
FROM end_dated_source
