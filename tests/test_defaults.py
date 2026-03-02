import sys
import os
from sqlglot import exp

# Add the package to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), ".")))

from datavault4sqlglot import HubGenerator, SourceModel, config

def test_defaults():
    # Set custom defaults in config (alias serves as default)
    config.ldts_alias = "CUSTOM_LDTS"
    config.rsrc_alias = "CUSTOM_RSRC"
    
    source = SourceModel(
        table_name="stg_orders",
        business_keys=["o_orderkey"]
    )
    
    # HubGenerator with no explicit hashkey (should use target_table + _h prefix or similar if we implemented it, 
    # but currently it uses the 'hashkey' init param)
    # Actually HubGenerator uses self.hashkey which we made Optional.
    # If self.hashkey is None, it might fail if not handled.
    
    generator = HubGenerator(
        target_table="order_h",
        source_models=[source],
        hashkey="hk_order_h"
    )
    
    sql = generator.generate_sql().sql()
    print("Generated SQL:")
    print(sql)
    
    # Check if defaults are used
    assert "CUSTOM_LDTS" in sql
    assert "CUSTOM_RSRC" in sql
    assert "hk_order_h" in sql
    
    print("Test passed!")

if __name__ == "__main__":
    test_defaults()
