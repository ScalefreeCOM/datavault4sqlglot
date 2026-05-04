-- STAGE -- use_rtrim=True — TRIM applied before hashing

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
  ) AS "HK_ORDER_H"
FROM "ORDERS"
