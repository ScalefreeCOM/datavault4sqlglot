-- REC-TRACK -- Incremental HWM — COALESCE handles empty target, LEFT JOIN for rsrc_static

WITH distinct_concated_target AS (
  SELECT
    CONCAT(CAST(hk_order AS VARCHAR(4000)), ldts, rsrc) AS concat
  FROM "rec_track_orders"
), max_ldts_per_rsrc_static_in_target AS (
  SELECT
    MAX(ldts) AS max_ldts,
    'SAP/ORDERS' AS rsrc_static
  FROM "rec_track_orders"
  WHERE
    rsrc LIKE 'SAP/ORDERS' AND ldts <> '9999-12-31'
), src_new_0 AS (
  SELECT DISTINCT
    hk_order AS hk_order,
    ldts AS ldts,
    CAST('SAP/ORDERS' AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('stg_orders') AS VARCHAR(4000)) AS stg
  FROM "stg_orders" AS src
  LEFT JOIN max_ldts_per_rsrc_static_in_target AS max
    ON max.rsrc_static LIKE 'SAP/ORDERS'
  WHERE
    src.ldts > COALESCE(max.max_ldts, '1970-01-01 00:00:00')
), records_to_insert AS (
  SELECT
    hk_order,
    ldts,
    rsrc,
    stg
  FROM src_new_0
  WHERE
    NOT ldts IN ('9999-12-31', '1970-01-01 00:00:00')
    AND NOT CONCAT(CAST(hk_order AS VARCHAR(4000)), ldts, rsrc) IN (SELECT
        concat
    FROM distinct_concated_target)
)
SELECT
  *
FROM records_to_insert
