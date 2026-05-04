-- STAGE -- sequence=SEQ_NUM — ROW_NUMBER() OVER () column

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
  ROW_NUMBER() OVER () AS "SEQ_NUM"
FROM "ORDERS"
