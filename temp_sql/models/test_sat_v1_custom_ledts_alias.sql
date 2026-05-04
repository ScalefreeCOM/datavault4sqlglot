-- SAT — sat_v1 — custom ledts_alias=LOAD_END_DATE, is_current_col=IS_LATEST

WITH end_dated_source AS (
  SELECT
    *,
    COALESCE(LEAD(ldts) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts), '9999-12-31') AS "LOAD_END_DATE"
  FROM "SAT_ORDER_DETAILS"
)
SELECT
  *,
  CASE WHEN LOAD_END_DATE = '9999-12-31' THEN TRUE ELSE FALSE END AS "IS_LATEST"
FROM end_dated_source
