-- PIT -- Satellite with ledts column — BETWEEN uses ledts directly, no LEAD

WITH pit_records AS (
  SELECT
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
                              REPLACE(
                                REPLACE(TRIM(CAST("HK_CUSTOMER_H" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'),
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
                              REPLACE(REPLACE(TRIM(CAST("SDTS" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
    ) AS "DIM_CUSTOMER_KEY",
    te.HK_CUSTOMER_H AS HK_CUSTOMER_H,
    snap.SDTS AS SDTS,
    COALESCE(sat_v1.HK_CUSTOMER_H, '00000000000000000000000000000000') AS hk_sat_v1,
    COALESCE(sat_v1.ldts, '0001-01-01') AS ldts_sat_v1
  FROM "HUB_CUSTOMER" AS te
  FULL OUTER JOIN "SNAP_DATES" AS snap
    ON 1 = 1
  LEFT JOIN (
    SELECT
      HK_CUSTOMER_H,
      ldts,
      ledts
    FROM "SAT_CUSTOMER_DETAILS_V1"
  ) AS sat_v1
    ON sat_v1.HK_CUSTOMER_H = te.HK_CUSTOMER_H
    AND snap.SDTS BETWEEN sat_v1.ldts AND sat_v1.ledts
), records_to_insert AS (
  SELECT DISTINCT
    *
  FROM pit_records
  ORDER BY
    SDTS
)
SELECT
  *
FROM records_to_insert
