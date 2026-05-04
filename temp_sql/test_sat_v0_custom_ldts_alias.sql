-- SAT v0 -- Config — custom ldts_alias=load_ts

WITH src_new AS (
  SELECT
    hk_order AS hk_order,
    hashdiff AS hashdiff,
    load_ts AS load_ts,
    rsrc AS rsrc
  FROM "stg_orders"
  WHERE
    load_ts > (
      SELECT
        COALESCE(MAX(load_ts), '0001-01-01')
      FROM "sat_orders"
      WHERE
        load_ts <> '9999-12-31'
    )
), deduplicated_numbered_source AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY hk_order ORDER BY load_ts) AS rn
  FROM src_new
  QUALIFY
    CASE
      WHEN hashdiff = LAG(hashdiff) OVER (PARTITION BY hk_order ORDER BY load_ts)
      THEN FALSE
      ELSE TRUE
    END
), latest_entries_in_sat AS (
  SELECT
    hk_order,
    hashdiff
  FROM "sat_orders"
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY hk_order ORDER BY load_ts DESC NULLS LAST) = 1
), records_to_insert AS (
  SELECT
    *
  FROM deduplicated_numbered_source
  WHERE
    NOT EXISTS(
      SELECT
        1
      FROM latest_entries_in_sat
      WHERE
        latest_entries_in_sat.hk_order = deduplicated_numbered_source.hk_order
        AND latest_entries_in_sat.hashdiff = deduplicated_numbered_source.hashdiff
        AND deduplicated_numbered_source.rn = 1
    )
)
SELECT
  *
FROM records_to_insert
