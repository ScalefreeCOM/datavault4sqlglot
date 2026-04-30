from datavault4sqlglot.generators.satellite_v1 import SatelliteV1Generator

generator = SatelliteV1Generator(
    source_satellite="SAT_ORDER_DETAILS",
    source_satellite_schema="DV_SCHEMA",
    source_satellite_database="DV_DB",
    parent_hash_key="HK_ORDER_H"
)

print(generator.to_sql())
