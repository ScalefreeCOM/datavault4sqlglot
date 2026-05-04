-- PIT — Full Load — 2 sats, refer_to_ghost_records=True (COALESCE to ghost key)

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
    COALESCE(sat_customer_details.HK_CUSTOMER_H, '00000000000000000000000000000000') AS hk_sat_customer_details,
    COALESCE(sat_customer_details.ldts, '0001-01-01') AS ldts_sat_customer_details,
    COALESCE(sat_customer_contact.HK_CUSTOMER_H, '00000000000000000000000000000000') AS hk_sat_customer_contact,
    COALESCE(sat_customer_contact.ldts, '0001-01-01') AS ldts_sat_customer_contact
  FROM "DV_DB"."RAW_VAULT"."HUB_CUSTOMER" AS te
  FULL OUTER JOIN "DV_DB"."CONTROL"."SNAP_DATES" AS snap
    ON 1 = 1
  LEFT JOIN (
    SELECT
      HK_CUSTOMER_H,
      ldts,
      COALESCE(LEAD(ldts) OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts), '9999-12-31') AS "ledts"
    FROM "DV_DB"."RAW_VAULT"."SAT_CUSTOMER_DETAILS"
  ) AS sat_customer_details
    ON sat_customer_details.HK_CUSTOMER_H = te.HK_CUSTOMER_H
    AND snap.SDTS BETWEEN sat_customer_details.ldts AND sat_customer_details.ledts
  LEFT JOIN (
    SELECT
      HK_CUSTOMER_H,
      ldts,
      COALESCE(LEAD(ldts) OVER (PARTITION BY HK_CUSTOMER_H ORDER BY ldts), '9999-12-31') AS "ledts"
    FROM "DV_DB"."RAW_VAULT"."SAT_CUSTOMER_CONTACT"
  ) AS sat_customer_contact
    ON sat_customer_contact.HK_CUSTOMER_H = te.HK_CUSTOMER_H
    AND snap.SDTS BETWEEN sat_customer_contact.ldts AND sat_customer_contact.ledts
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
