-- EFF-SAT — Multi-Batch Full Load (CROSS JOIN history × load_dates, LAG dedup)

WITH source_data AS (
  SELECT
    HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDER_CUSTOMER" AS src
  WHERE
    NOT LOAD_DATE IN ('0001-01-01', '9999-12-31')
), hashkeys AS (
  SELECT
    HK_ORDER_CUSTOMER_L,
    MIN(ldts) AS first_appearance
  FROM source_data
  GROUP BY
    HK_ORDER_CUSTOMER_L
), load_dates AS (
  SELECT DISTINCT
    ldts
  FROM source_data
), history AS (
  SELECT
    hk.HK_ORDER_CUSTOMER_L,
    ld.ldts
  FROM hashkeys AS hk
  CROSS JOIN load_dates AS ld
  WHERE
    ld.ldts >= hk.first_appearance
), is_active AS (
  SELECT
    h.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    h.ldts AS ldts,
    COALESCE(src.rsrc, 'SYSTEM') AS rsrc,
    CASE WHEN src.HK_ORDER_CUSTOMER_L IS NULL THEN 0 ELSE 1 END AS is_active
  FROM history AS h
  LEFT JOIN source_data AS src
    ON src.HK_ORDER_CUSTOMER_L = h.HK_ORDER_CUSTOMER_L AND src.ldts = h.ldts
), deduplicated_incoming AS (
  SELECT
    *
  FROM is_active
  QUALIFY
    CASE
      WHEN is_active = LAG(is_active) OVER (PARTITION BY HK_ORDER_CUSTOMER_L ORDER BY ldts)
      THEN FALSE
      ELSE TRUE
    END
), records_to_insert AS (
  SELECT
    *
  FROM deduplicated_incoming
)
SELECT
  ri.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
  ri.ldts AS ldts,
  ri.rsrc AS rsrc,
  CAST(ri.is_active AS BOOLEAN) AS "is_active"
FROM records_to_insert AS ri
