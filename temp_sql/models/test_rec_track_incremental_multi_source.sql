-- REC-TRACK — Incremental — Multi Source (SAP + WEB), per-source HWM

WITH distinct_concated_target AS (
  SELECT
    CONCAT(CAST(HK_ORDER_H AS VARCHAR(4000)), ldts, rsrc) AS concat
  FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
), rsrc_static_unionized AS (
  SELECT
    HK_ORDER_H,
    ldts,
    'SAP/ORDERS' AS rsrc_static
  FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
  WHERE
    rsrc LIKE 'SAP/ORDERS'
  UNION ALL
  SELECT
    HK_ORDER_H,
    ldts,
    'WEB/%' AS rsrc_static
  FROM "DV_DB"."RAW_VAULT"."REC_TRACK_SAT_ORDER"
  WHERE
    rsrc LIKE 'WEB/%'
), max_ldts_per_rsrc_static_in_target AS (
  SELECT
    rsrc_static,
    MAX(ldts) AS max_ldts
  FROM rsrc_static_unionized
  WHERE
    ldts <> '9999-12-31'
  GROUP BY
    rsrc_static
), src_new_0 AS (
  SELECT DISTINCT
    HK_ORDER_H AS HK_ORDER_H,
    LOAD_DATE AS ldts,
    CAST('SAP/ORDERS' AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('STG_SAP_ORDERS') AS VARCHAR(4000)) AS stg
  FROM "RAW_DB"."STAGE"."STG_SAP_ORDERS" AS src
  LEFT JOIN max_ldts_per_rsrc_static_in_target AS max
    ON max.rsrc_static = 'SAP/ORDERS'
  WHERE
    src.LOAD_DATE > COALESCE(max.max_ldts, '0001-01-01')
), src_new_1 AS (
  SELECT DISTINCT
    HK_ORDER_H AS HK_ORDER_H,
    LOAD_DATE AS ldts,
    CAST('WEB/%' AS VARCHAR(4000)) AS rsrc,
    CAST(UPPER('STG_WEB_ORDERS') AS VARCHAR(4000)) AS stg
  FROM "RAW_DB"."STAGE"."STG_WEB_ORDERS" AS src
  LEFT JOIN max_ldts_per_rsrc_static_in_target AS max
    ON max.rsrc_static = 'WEB/%'
  WHERE
    src.LOAD_DATE > COALESCE(max.max_ldts, '0001-01-01')
), source_new_union AS (
  SELECT
    *
  FROM src_new_0
  UNION ALL
  SELECT
    *
  FROM src_new_1
), records_to_insert AS (
  SELECT
    HK_ORDER_H,
    ldts,
    rsrc,
    stg
  FROM source_new_union
  WHERE
    NOT ldts IN ('9999-12-31', '0001-01-01')
    AND NOT CONCAT(CAST(HK_ORDER_H AS VARCHAR(4000)), ldts, rsrc) IN (SELECT
        concat
    FROM distinct_concated_target)
)
SELECT
  *
FROM records_to_insert
