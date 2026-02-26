from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceModel

source = SourceModel(
    database="RAW_DB",
    schema="RAW_SCHEMA",
    table_name="ORDERS",
    hashed_columns={
        "hk_h_order": ["o_orderkey"],
        "hk_h_customer": ["o_custkey"],
        "hk_l_order_customer": ["o_orderkey", "o_custkey"],
        "hd_order_details": {
            "is_hashdiff": True,
            "columns": ["o_orderstatus", "o_orderpriority", "o_shippriority"]
        }
    },
    derived_columns={
        "load_date": "CURRENT_TIMESTAMP()",
        "record_source": "'SYSTEM'"
    }
)

generator = StageGenerator(source_model=source)
print(generator.to_sql())
