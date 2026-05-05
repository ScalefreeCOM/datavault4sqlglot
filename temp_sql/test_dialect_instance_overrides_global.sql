-- DIALECT -- instance dialect=duckdb overrides global=snowflake

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
                        REPLACE(REPLACE(TRIM(CAST("id" AS TEXT(4000))), '\\', '\\\\'), '"', '\"'),
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
          ) AS TEXT(4000)),
          '^^'
        )
      )
    ),
    '00000000000000000000000000000000'
  ) AS "hk"
FROM "orders"
