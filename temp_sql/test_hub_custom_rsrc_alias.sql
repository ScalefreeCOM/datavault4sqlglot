-- HUB -- Config — custom rsrc_alias=rec_src

WITH src_new_0 AS (
  SELECT
    hk_order AS hk_order,
    order_id,
    ldts AS ldts,
    rec_src AS rec_src
  FROM "stg_orders"
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM src_new_0
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY hk_order ORDER BY ldts) = 1
)
SELECT
  *
FROM earliest_hk_over_all_sources
