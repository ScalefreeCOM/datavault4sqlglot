-- SAT — sat_v0 — Incremental, disable_hwm=True (no time filter)

WITH src_new AS (
  SELECT
    HK_ORDER_H AS HK_ORDER_H,
    HK_ORDER_DETAILS_D AS HK_ORDER_DETAILS_D,
    ORDER_STATUS,
    TOTAL_PRICE,
    ORDER_DATE,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDERS"
), deduplicated_numbered_source AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_H ORDER BY ldts) AS rn
  FROM src_new
  QUALIFY
    CASE
      WHEN HK_ORDER_DETAILS_D = LAG(HK_ORDER_DETAILS_D) OVER (PARTITION BY HK_ORDER_H ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
), latest_entries_in_sat AS (
  SELECT
    HK_ORDER_H,
    HK_ORDER_DETAILS_D
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
        AND latest_entries_in_sat.HK_ORDER_DETAILS_D = deduplicated_numbered_source.HK_ORDER_DETAILS_D
        AND deduplicated_numbered_source.rn = 1
    )
)
SELECT
  *
FROM records_to_insert
