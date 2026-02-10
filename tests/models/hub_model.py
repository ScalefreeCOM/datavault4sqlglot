from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata.source import SourceTable

source_1 = SourceTable(
    name="raw.orders",
    business_keys=["order_id"],
    load_date_col="load_date",
    record_source_col="record_source"
)

source_2 = SourceTable(
    name="raw.web_orders",
    business_keys=["web_order_id"],
    load_date_col="load_tss",
    record_source_col="rsrc"
)

generator = HubGenerator(
    target_table_name="dv.hub_orders",
    source_models=[source_1,source_2]
)

print(generator.generate_sql().sql(pretty=True))
