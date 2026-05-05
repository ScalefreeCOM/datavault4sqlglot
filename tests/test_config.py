from datavault4sqlglot import config, HubGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel
import pytest

def test_config_override():
    # 1. Check default values
    assert config.ldts_alias == "ldts"
    assert config.hash == "MD5"

    # 2. Define a source
    source = SourceBinding(
        source=SourceModel(
            database="RAW",
            schema="STG",
            table_name="ORDERS",
            load_date_col="LOAD_TS",
            record_source_col="RECORD_SRC",
        ),
        business_keys=["ORDER_ID"],
    )

    # 3. Generate Hub SQL with defaults
    gen = HubGenerator(target_table="HUB_ORDERS", sources=[source], hashkey="HK_ORDERS")
    sql_default = gen.generate_sql().sql()
    
    assert "ldts" in sql_default
    assert "HK_ORDERS" in sql_default
    
    # 4. Override global config
    config.ldts_alias = "load_date_timestamp"
    config.hash = "SHA256"
    
    # 5. Generate Hub SQL again
    sql_overridden = gen.generate_sql().sql()
    
    assert "load_date_timestamp" in sql_overridden
    assert "HK_ORDERS" in sql_overridden
    
    # Cleanup (reset defaults for other tests)
    config.ldts_alias = "ldts"
    config.hash = "MD5"

if __name__ == "__main__":
    pytest.main([__file__])
