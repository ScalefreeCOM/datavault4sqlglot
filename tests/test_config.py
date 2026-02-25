from datavault4sqlglot import config, HubGenerator
from datavault4sqlglot.metadata import SourceModel
import pytest

def test_config_override():
    # 1. Check default values
    assert config.ldts_alias == "ldts"
    assert config.hash == "MD5"
    
    # 2. Define a source
    source = SourceModel(
        database="RAW",
        schema="STG",
        table_name="ORDERS",
        business_keys=["ORDER_ID"],
        load_date_col="LOAD_TS",
        record_source_col="RECORD_SRC"
    )
    
    # 3. Generate Hub SQL with defaults
    gen = HubGenerator(target_table="HUB_ORDERS", source_models=[source])
    sql_default = gen.generate_sql().sql()
    
    assert "ldts" in sql_default
    assert "hash_key" in sql_default
    
    # 4. Override global config
    config.ldts_alias = "load_date_timestamp"
    config.hash = "SHA256"
    
    # 5. Generate Hub SQL again
    sql_overridden = gen.generate_sql().sql()
    
    assert "load_date_timestamp" in sql_overridden
    assert "hash_key" in sql_overridden
    
    # Cleanup (reset defaults for other tests)
    config.ldts_alias = "ldts"
    config.hash = "MD5"

if __name__ == "__main__":
    pytest.main([__file__])
