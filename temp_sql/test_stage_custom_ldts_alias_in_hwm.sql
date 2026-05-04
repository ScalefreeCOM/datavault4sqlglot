-- STAGE -- custom ldts_alias=load_ts in incremental HWM filter

SELECT *, NULLIF(LOWER(MD5(NULLIF(CAST(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(UPPER(CONCAT(COALESCE(CONCAT('\"', REPLACE(REPLACE(REPLACE(TRIM(CAST("order_id" AS VARCHAR(4000))), '\\', '\\\\'), '"', '\"'), '^^', '--'), '\"'), '^^'))), CHR(9), ''), CHR(10), ''), CHR(11), ''), CHR(13), '') AS VARCHAR(4000)), '^^'))), '00000000000000000000000000000000') AS "hk_order" FROM "raw.orders" WHERE load_ts > (SELECT MAX(load_ts) FROM "stage_view" WHERE load_ts <> '9999-12-31')
