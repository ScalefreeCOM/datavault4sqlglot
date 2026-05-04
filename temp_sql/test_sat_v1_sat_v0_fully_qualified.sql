-- SAT v1 -- sat_v0 fully qualified: my_db.raw_vault.sat_orders

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM "my_db"."raw_vault"."sat_orders"
)
SELECT
  *,
  CASE WHEN ledts = '9999-12-31' THEN TRUE ELSE FALSE END AS "is_current"
FROM end_dated_source
