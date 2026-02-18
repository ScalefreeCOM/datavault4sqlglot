import pytest
from sqlglot import exp

from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata.source import SourceTable


@pytest.fixture
def source_model_single():
    return SourceTable(
        name="raw.orders",
        business_keys=["order_id"],
        load_date_col="load_date",
        record_source_col="record_source"
    )

@pytest.fixture
def source_model_multi_1():
    return SourceTable(
        name="raw.web_orders",
        business_keys=["web_order_id"],
        load_date_col="load_tss",
        record_source_col="rsrc"
    )

@pytest.fixture
def source_model_multi_2():
    return SourceTable(
        name="raw.store_orders",
        business_keys=["store_order_id"],
        load_date_col="load_tss",
        record_source_col="rsrc"
    )

def test_hub_single_source(source_model_single):
    generator = HubGenerator(
        target_table_name="dv.hub_orders",
        source_models=[source_model_single]
    )
    
    generated_sql_obj = generator.generate_sql()
    generated_sql = generated_sql_obj.sql()

    # Simple string contains checks for now
    assert "INSERT INTO" not in generated_sql # The generator only generates the SELECT part usually? 
    # Wait, the generator returns the SELECT query. 
    
    assert "MD5" in generated_sql
    assert "UPPER" in generated_sql
    assert "order_id" in generated_sql
    assert "raw.orders" in generated_sql
    assert "dv.hub_orders" in generated_sql
    # Qualification check
    assert "ROW_NUMBER() OVER" in generated_sql or "QUALIFY" in generated_sql

def test_hub_multi_source_union(source_model_multi_1, source_model_multi_2):
    generator = HubGenerator(
        target_table_name="dv.hub_orders",
        source_models=[source_model_multi_1, source_model_multi_2]
    )
    
    generated_sql_obj = generator.generate_sql()
    generated_sql = generated_sql_obj.sql()
    
    assert "UNION" in generated_sql
    assert "raw.web_orders" in generated_sql
    assert "raw.store_orders" in generated_sql
    assert "web_order_id" in generated_sql
    assert "store_order_id" in generated_sql

def test_hub_incremental_filter(source_model_single):
    generator = HubGenerator(
        target_table_name="dv.hub_orders",
        source_models=[source_model_single]
    )
    
    generated_sql_obj = generator.generate_sql()
    generated_sql = generated_sql_obj.sql()
    
    # Check for target lookup 
    assert "dv.hub_orders" in generated_sql
    # Check for NOT IN / NOT EXISTS logic
    # sqlglot might generate "NOT column IN ..." or "NOT EXISTS"
    assert "NOT" in generated_sql
