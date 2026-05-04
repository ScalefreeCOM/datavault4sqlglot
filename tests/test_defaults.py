import sys
import os
from sqlglot import exp

# Add the package to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), ".")))

from datavault4sqlglot import HubGenerator, config
from datavault4sqlglot.metadata import SourceBinding, SourceModel

def test_defaults():
    # Set custom defaults in config (alias serves as default)
    config.ldts_alias = "CUSTOM_LDTS"
    config.rsrc_alias = "CUSTOM_RSRC"

    source = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        business_keys=["o_orderkey"],
    )

    generator = HubGenerator(
        target_table="order_h",
        sources=[source],
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
