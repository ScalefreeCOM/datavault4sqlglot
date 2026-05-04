-- EFF-SAT -- Single-Batch Incremental (LEFT JOIN current_status, disappeared -> is_active=0)

WITH source_data AS (
  SELECT
    HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDER_CUSTOMER" AS src
  WHERE
    NOT LOAD_DATE IN ('0001-01-01', '9999-12-31')
    AND LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '0001-01-01')
      FROM "DV_DB"."RAW_VAULT"."EFF_SAT_ORDER_CUSTOMER"
      WHERE
        ldts <> '9999-12-31'
    )
), current_status AS (
  SELECT
    HK_ORDER_CUSTOMER_L,
    is_active,
    rsrc
  FROM "DV_DB"."RAW_VAULT"."EFF_SAT_ORDER_CUSTOMER"
  QUALIFY
    ROW_NUMBER() OVER (PARTITION BY HK_ORDER_CUSTOMER_L ORDER BY ldts DESC NULLS LAST) = 1
), new_hashkeys AS (
  SELECT DISTINCT
    src.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    src.ldts AS ldts,
    src.rsrc AS rsrc,
    1 AS is_active
  FROM source_data AS src
  LEFT JOIN current_status AS cs
    ON src.HK_ORDER_CUSTOMER_L = cs.HK_ORDER_CUSTOMER_L
    AND cs.is_active = CAST(1 AS BOOLEAN)
  WHERE
    cs.HK_ORDER_CUSTOMER_L IS NULL
), disappeared_hashkeys AS (
  SELECT DISTINCT
    cs.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    ldts.min_ldts AS ldts,
    'SYSTEM' AS rsrc,
    0 AS is_active
  FROM current_status AS cs
  LEFT JOIN (
    SELECT
      MIN(ldts) AS min_ldts
    FROM source_data
  ) AS ldts
    ON 1 = 1
  WHERE
    NOT EXISTS(
      SELECT
        1
      FROM source_data
      WHERE
        source_data.HK_ORDER_CUSTOMER_L = cs.HK_ORDER_CUSTOMER_L
    )
    AND cs.is_active = CAST(1 AS BOOLEAN)
    AND NOT ldts.min_ldts IS NULL
), records_to_insert AS (
  SELECT
    *
  FROM new_hashkeys
  UNION ALL
  SELECT
    *
  FROM disappeared_hashkeys
)
SELECT
  ri.HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
  ri.ldts AS ldts,
  ri.rsrc AS rsrc,
  CAST(ri.is_active AS BOOLEAN) AS "is_active"
FROM records_to_insert AS ri
WHERE
  NOT EXISTS(
    SELECT
      1
    FROM "DV_DB"."RAW_VAULT"."EFF_SAT_ORDER_CUSTOMER" AS t
    WHERE
      t.HK_ORDER_CUSTOMER_L = ri.HK_ORDER_CUSTOMER_L AND t.ldts = ri.ldts
  )
