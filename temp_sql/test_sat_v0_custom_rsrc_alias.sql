-- SAT v0 -- Config — custom rsrc_alias=rec_src

WITH src_new AS (
  SELECT
    hk_order AS hk_order,
    hashdiff AS hashdiff,
    ldts AS ldts,
    rec_src AS rec_src
  FROM "stg_orders"
), deduplicated_numbered_source AS (
  SELECT
    *
  FROM src_new
  QUALIFY
    CASE
      WHEN hashdiff = LAG(hashdiff) OVER (PARTITION BY hk_order ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
)
SELECT
  *
FROM deduplicated_numbered_source
