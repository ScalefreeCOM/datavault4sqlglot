-- STAGE -- Incremental — HWM WHERE ldts > MAX(ldts) from target

WITH derived_columns_cte AS (
  SELECT
    *,
    CURRENT_TIMESTAMP() AS "LOAD_DATE",
    'ERP/ORDERS' AS "RECORD_SOURCE"
  FROM (
    SELECT
      *
    FROM "RAW_DB"."RAW_SCHEMA"."ORDERS"
    WHERE
      ldts > (
        SELECT
          MAX(ldts)
        FROM "stage_view"
        WHERE
          ldts <> '9999-12-31'
      )
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
                            REPLACE(REPLACE(TRIM(CAST("O_CUSTKEY" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
  ) AS "HK_CUSTOMER_H",
  NULLIF(
    LOWER(
      MD5(
        NULLIF(
          CAST(REGEXP_REPLACE(
            REGEXP_REPLACE(
              REGEXP_REPLACE(
                REGEXP_REPLACE(
                  UPPER(
                    CONCAT_WS(
                      '||',
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
                      ),
                      COALESCE(
                        CONCAT(
                          '\\"',
                          REPLACE(
                            REPLACE(REPLACE(TRIM(CAST("O_CUSTKEY" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
          '^^||^^'
        )
      )
    ),
    '00000000000000000000000000000000'
  ) AS "HK_L_ORD_CUST",
  NULLIF(
    LOWER(
      MD5(
        NULLIF(
          CAST(REGEXP_REPLACE(
            REGEXP_REPLACE(
              REGEXP_REPLACE(
                REGEXP_REPLACE(
                  CONCAT_WS(
                    '||',
                    COALESCE(
                      CONCAT(
                        '\\"',
                        REPLACE(
                          REPLACE(
                            REPLACE(TRIM(CAST("O_ORDERSTATUS" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'),
                            '"',
                            '\\"'
                          ),
                          '^^',
                          '--'
                        ),
                        '\\"'
                      ),
                      '^^'
                    ),
                    COALESCE(
                      CONCAT(
                        '\\"',
                        REPLACE(
                          REPLACE(
                            REPLACE(TRIM(CAST("O_ORDERPRIORITY" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'),
                            '"',
                            '\\"'
                          ),
                          '^^',
                          '--'
                        ),
                        '\\"'
                      ),
                      '^^'
                    ),
                    COALESCE(
                      CONCAT(
                        '\\"',
                        REPLACE(
                          REPLACE(
                            REPLACE(TRIM(CAST("O_SHIPPRIORITY" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'),
                            '"',
                            '\\"'
                          ),
                          '^^',
                          '--'
                        ),
                        '\\"'
                      ),
                      '^^'
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
          '^^||^^||^^'
        )
      )
    ),
    '00000000000000000000000000000000'
  ) AS "HD_ORDER_DETAILS"
FROM "derived_columns_cte"
