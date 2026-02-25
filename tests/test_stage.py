import pytest
from sqlglot import exp

from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceModel


@pytest.fixture
def stage_source_basic():
    return SourceModel(
        table_name="raw.orders",
        hashed_columns={
            "hk_order_id": ["order_id"],
            "hk_customer_id": ["customer_id"]
        },
        derived_columns={
            "load_date": "CURRENT_TIMESTAMP()",
            "record_source": "'SYSTEM'"
        }
    )

def test_stage_generation(stage_source_basic):
    generator = StageGenerator(source_model=stage_source_basic)
    sql_obj = generator.generate_sql()
    sql = sql_obj.sql()

    # Derived columns CTE check
    assert "derived_columns_cte" in sql
    assert "CURRENT_TIMESTAMP()" in sql
    
    # Selection from CTE
    assert "SELECT" in sql
    
    # Hashing Logic Check
    assert "MD5" in sql
    assert "UPPER" in sql
    assert "hk_order_id" in sql
    
    # Clean column check (Concat quotes, replace, etc)
    assert "COALESCE" in sql 
    
def test_stage_multi_column_hash():
    source = SourceModel(
        table_name="raw.line_items",
        hashed_columns={
            "hk_link": ["order_id", "item_id"]
        }
    )
    generator = StageGenerator(source_model=source)
    sql = generator.generate_sql().sql()
    
    # Check for concatenation
    assert "||" in sql or "CONCAT" in sql
    assert "order_id" in sql
    assert "item_id" in sql
