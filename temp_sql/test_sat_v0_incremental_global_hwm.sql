-- SAT v0 -- Incremental — global HWM (COALESCE MAX from target)

WITH src_new AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    HD_ORDER_DETAILS AS HD_ORDER_DETAILS,
    ORDER_STATUS,
    TOTAL_PRICE,
    ORDER_DATE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDERS"
  WHERE
    LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '0001-01-01')
      FROM "DV_DB"."RAW_VAULT"."SAT_ORDER_DETAILS"
      WHERE
        ldts <> '9999-12-31'
    )
), deduplicated_numbered_source AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_H ORDER BY ldts) AS rn
  FROM src_new
  QUALIFY
    CASE
      WHEN HD_ORDER_DETAILS = LAG(HD_ORDER_DETAILS) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
), latest_entries_in_sat AS (
  SELECT
    HK_ORDER_H,
    HD_ORDER_DETAILS
  FROM "DV_DB"."RAW_VAULT"."SAT_ORDER_DETAILS"
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_H ORDER BY ldts DESC NULLS LAST) = 1
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
        latest_entries_in_sat.HK_ORDER_H = deduplicated_numbered_source.HK_ORDER_H
        AND latest_entries_in_sat.HD_ORDER_DETAILS = deduplicated_numbered_source.HD_ORDER_DETAILS
        AND deduplicated_numbered_source.rn = 1
    )
)
SELECT
  *
FROM records_to_insert
