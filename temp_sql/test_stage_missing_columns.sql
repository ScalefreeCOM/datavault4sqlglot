-- STAGE -- missing_columns — CAST(NULL AS dtype) for schema evolution

WITH derived_columns_cte AS (
  SELECT
    *,
    CURRENT_TIMESTAMP() AS "LOAD_DATE"
  FROM (
    SELECT
      *
    FROM "ORDERS"
  ) AS _src
)
SELECT
  *,
  NULLIF(
    LOWER(
      MD5(
        NULLIF(
          CAST(REGEXP_REPLACE(
            REGEXP_REPLACE(
              REGEXP_REPLACE(
                REGEXP_REPLACE(
                  UPPER(
                    CONCAT(
                      COALESCE(
                        CONCAT(
                          '\\"',
                          REPLACE(
                            REPLACE(REPLACE(TRIM(CAST("O_ORDERKEY" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
                            '^^',
                            '--'
                          ),
                          '\\"'
                        ),
                        '^^'
                      )
                    )
                  ),
                  CHR(  9),
                  ''
                ),
                CHR(  10),
                ''
              ),
              CHR(  11),
              ''
            ),
            CHR(  13),
            ''
          ) AS VARCHAR(4000)),
          '^^'
        )
      )
    ),
    '00000000000000000000000000000000'
  ) AS "HK_ORDER_H",
  CAST(NULL AS BOOLEAN) AS "LEGACY_FLAG",
  CAST(NULL AS VARCHAR) AS "REGION_CODE",
  CAST(NULL AS DECIMAL) AS "DISCOUNT_RATE"
FROM "derived_columns_cte"
