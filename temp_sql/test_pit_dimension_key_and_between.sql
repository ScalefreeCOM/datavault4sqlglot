-- PIT -- Dimension key hash + BETWEEN ldts/ledts

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
                              REPLACE(REPLACE(TRIM(CAST("hk_order" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
                              REPLACE(REPLACE(TRIM(CAST("sdts" AS VARCHAR(4000))), '\\\\', '\\\\\\\\'), '"', '\\"'),
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
    ) AS "pk_pit",
    te.hk_order AS hk_order,
    snap.sdts AS sdts,
    COALESCE(sat_orders.hk_order, '00000000000000000000000000000000') AS hk_sat_orders,
    COALESCE(sat_orders.ldts, '0001-01-01') AS ldts_sat_orders,
    COALESCE(sat_details.hk_order, '00000000000000000000000000000000') AS hk_sat_details,
    COALESCE(sat_details.ldts, '0001-01-01') AS ldts_sat_details
  FROM "hub_orders" AS te
  FULL OUTER JOIN "snap_dates" AS snap
    ON 1 = 1
  LEFT JOIN (
    SELECT
      hk_order,
      ldts,
      COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '9999-12-31') AS "ledts"
    FROM "sat_orders"
  ) AS sat_orders
    ON sat_orders.hk_order = te.hk_order
    AND snap.sdts BETWEEN sat_orders.ldts AND sat_orders.ledts
  LEFT JOIN (
    SELECT
      hk_order,
      ldts,
      COALESCE(LEAD(ldts) OVER (PARTITION BY hk_order ORDER BY ldts), '9999-12-31') AS "ledts"
    FROM "sat_orders_details"
  ) AS sat_details
    ON sat_details.hk_order = te.hk_order
    AND snap.sdts BETWEEN sat_details.ldts AND sat_details.ledts
), records_to_insert AS (
  SELECT DISTINCT
    *
  FROM pit_records
  ORDER BY
    sdts
)
SELECT
  *
FROM records_to_insert
