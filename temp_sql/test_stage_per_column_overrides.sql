-- STAGE -- Per-column overrides — HK: no UPPER + no TRIM; HD: default hashdiff settings

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
                  CONCAT(
                    COALESCE(
                      CONCAT(
                        '\\"',
                        REPLACE(
                          REPLACE(REPLACE(CAST("O_ORDERKEY" AS VARCHAR(4000)), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
                          REPLACE(REPLACE(TRIM(CAST("O_TOTALPRICE" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
          '^^||^^'
        )
      )
    ),
    '00000000000000000000000000000000'
  ) AS "HD_DETAILS"
FROM "ORDERS"
