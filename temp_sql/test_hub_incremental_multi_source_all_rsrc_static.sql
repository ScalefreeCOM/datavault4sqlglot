-- HUB -- Incremental — Multi Source, all rsrc_static (per-source HWM)

WITH max_ldts_per_rsrc_static_in_target AS (
  SELECT
    MAX(ldts) AS max_ldts,
    'SAP/ORDERS' AS rsrc_static
  FROM "DV_DB"."RAW_VAULT"."HUB_ORDER"
  WHERE
    rsrc LIKE 'SAP/ORDERS' AND ldts <> '9999-12-31'
  UNION ALL
  SELECT
    MAX(ldts) AS max_ldts,
    'WEB/%' AS rsrc_static
  FROM "DV_DB"."RAW_VAULT"."HUB_ORDER"
  WHERE
    rsrc LIKE 'WEB/%' AND ldts <> '9999-12-31'
), src_new_0 AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    SAP_ORDER_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_SAP_ORDERS"
  WHERE
    RECORD_SOURCE LIKE 'SAP/ORDERS'
    AND LOAD_DATE > (
      SELECT
        COALESCE(MAX(max_ldts), '0001-01-01')
      FROM max_ldts_per_rsrc_static_in_target
      WHERE
        rsrc_static LIKE 'SAP/ORDERS'
    )
), src_new_1 AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    WEB_ORDER_ID,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_WEB_ORDERS"
  WHERE
    RECORD_SOURCE LIKE 'WEB/%'
    AND LOAD_DATE > (
      SELECT
        COALESCE(MAX(max_ldts), '0001-01-01')
      FROM max_ldts_per_rsrc_static_in_target
      WHERE
        rsrc_static LIKE 'WEB/%'
    )
), source_new_union AS (
  SELECT
    *
  FROM src_new_0
  UNION ALL
  SELECT
    *
  FROM src_new_1
), earliest_hk_over_all_sources AS (
  SELECT
    *
  FROM source_new_union
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_H ORDER BY ldts) = 1
), distinct_target_hashkeys AS (
  SELECT
    HK_ORDER_H
  FROM "DV_DB"."RAW_VAULT"."HUB_ORDER"
), records_to_insert AS (
  SELECT
    *
  FROM earliest_hk_over_all_sources
  WHERE
    NOT HK_ORDER_H IN (SELECT
        HK_ORDER_H
    FROM distinct_target_hashkeys)
)
SELECT
  *
FROM records_to_insert
