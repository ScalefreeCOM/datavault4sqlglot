-- EFF-SAT -- Incremental HWM — COALESCE(MAX(ldts), boa) handles empty target

WITH source_data AS (
  SELECT
    HK_ORDER_CUSTOMER_L AS HK_ORDER_CUSTOMER_L,
    LOAD_DATE AS ldts,
    RECORD_SOURCE AS rsrc
  FROM "RAW_DB"."STAGE"."STG_ORDER_CUSTOMER" AS src
  WHERE
    NOT LOAD_DATE IN ('1970-01-01 00:00:00', '9999-12-31')
    AND LOAD_DATE > (
      SELECT
        COALESCE(MAX(ldts), '1970-01-01 00:00:00')
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
    FROM deduplicated_incoming
  ) AS ldts
    ON 1 = 1
  LEFT JOIN deduplicated_incoming AS src
    ON src.HK_ORDER_CUSTOMER_L = cs.HK_ORDER_CUSTOMER_L AND src.ldts = ldts.min_ldts
  WHERE
    cs.is_active = CAST(1 AS BOOLEAN)
    AND src.HK_ORDER_CUSTOMER_L IS NULL
    AND NOT ldts.min_ldts IS NULL
), records_to_insert AS (
  SELECT
    di."*"
  FROM deduplicated_incoming AS di
  WHERE
    NOT EXISTS(
      SELECT
        1
      FROM current_status
      WHERE
        current_status.HK_ORDER_CUSTOMER_L = di.HK_ORDER_CUSTOMER_L
        AND CAST(di.is_active AS BOOLEAN) = current_status.is_active
        AND di.ldts = (
          SELECT
            MIN(ldts)
          FROM deduplicated_incoming
        )
    )
    AND di.ldts > (
      SELECT
        MAX(ldts)
      FROM "DV_DB"."RAW_VAULT"."EFF_SAT_ORDER_CUSTOMER"
    )
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
