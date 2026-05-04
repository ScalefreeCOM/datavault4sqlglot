-- SAT — sat_v1 — add_is_current=False (only ledts, no flag)

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts), '9999-12-31') AS "ledts"
  FROM "SAT_ORDER_DETAILS"
)
SELECT
  *
FROM end_dated_source
