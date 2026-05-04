-- HUB -- Config — custom ldts_alias=load_ts

WITH src_new_0 AS (
  SELECT
    hk_order AS hk_order,
    order_id,
    load_ts AS load_ts,
    rsrc AS rsrc
  FROM "stg_orders"
  WHERE
    load_ts > (
      SELECT
        COALESCE(MAX(load_ts), '0001-01-01')
      FROM "hub_orders"
      WHERE
        load_ts <> '9999-12-31'
    )
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM src_new_0
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY hk_order ORDER BY load_ts) = 1
), distinct_target_hashkeys AS (
  SELECT
    hk_order
  FROM "hub_orders"
), records_to_insert AS (
  SELECT
    *
  FROM earliest_hk_over_all_sources
  WHERE
    NOT hk_order IN (SELECT
        hk_order
    FROM distinct_target_hashkeys)
)
SELECT
  *
FROM records_to_insert
