-- DIALECT -- global config.dialect=postgres

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
                    COALESCE(
                      '\"' || REPLACE(
                        REPLACE(REPLACE(TRIM(CAST("id" AS VARCHAR(4000))), '\\', '\\\\'), '"', '\"'),
                        '^^',
                        '--'
                      ) || '\"',
                      '^^'
                    )
                  ),
                  CHR(  9),
                  '',
                  'g'
                ),
                CHR(  10),
                '',
                'g'
              ),
              CHR(  11),
              '',
              'g'
            ),
            CHR(  13),
            '',
            'g'
          ) AS VARCHAR(4000)),
          '^^'
        )
      )
    ),
    '00000000000000000000000000000000'
  ) AS "hk"
FROM "orders"
