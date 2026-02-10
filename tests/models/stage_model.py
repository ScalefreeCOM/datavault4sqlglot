from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata.stage import StageSource

source = StageSource(
    source_model="raw.orders",
    hashed_columns={
        "hk_order_id": ["order_id", "customer_id"],
        "hk_customer_id": ["customer_id"]
    },
    derived_columns={
        "load_date": "CURRENT_TIMESTAMP()",
        "record_source": "'SYSTEM'"
    }
)

generator = StageGenerator(source_model=source)
print(generator.generate_sql().sql(pretty=True))
