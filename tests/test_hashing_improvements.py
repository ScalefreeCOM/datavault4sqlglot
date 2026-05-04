import pytest
from sqlglot import exp
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import StageModel

def test_hashing_improvements():
    source = StageModel(
        table_name="raw.orders",
        hashed_columns={
            "hk_order_id": ["order_id"]
        }
    )
    generator = StageGenerator(source_model=source)
    sql = generator.generate_sql().sql()

    # 1. Column identifiers are quoted
    assert '"order_id"' in sql

    # 2. NULL columns return the ghost-record sentinel '^^' (COALESCE, not NULLIF)
    assert "COALESCE" in sql

    # 3. Special characters stripped via REGEXP_REPLACE + CHR() calls
    assert "REGEXP_REPLACE" in sql
    assert "CHR(" in sql

    # 4. Concatenation is UPPER-cased before hashing
    assert "UPPER" in sql

    print("\nGenerated SQL snippet:")
    print(sql)

if __name__ == "__main__":
    test_hashing_improvements()
