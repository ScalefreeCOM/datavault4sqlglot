import pytest
from sqlglot import exp
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceModel

def test_hashing_improvements():
    source = SourceModel(
        table_name="raw.orders",
        hashed_columns={
            "hk_order_id": ["order_id"]
        }
    )
    generator = StageGenerator(source_model=source)
    sql = generator.generate_sql().sql()
    
    # 1. Quoted column names
    # Expecting CAST("order_id" AS VARCHAR(4000))
    assert '"order_id"' in sql
    
    # 2. IFNULL usage
    # Expecting IFNULL(..., '^^') and IFNULL(..., '0000...')
    assert "IFNULL" in sql
    assert "COALESCE" not in sql
    
    # 3. REGEXP_REPLACE usage
    assert "REGEXP_REPLACE" in sql
    assert r"[\x09\x0a\x0b\x0d]" in sql
    
    # Verify the structure roughly
    # MD5(IFNULL(LOWER(MD5(NULLIF(CAST(UPPER(REPLACE(REPLACE(REPLACE(REPLACE(CONCAT(IFNULL(CONCAT('\"', CAST(\"order_id\" AS VARCHAR(4000)), '\"'), '^^')), ''), CHAR(9), ''), CHAR(10), ''), CHAR(11), ''), CHAR(13), '')) AS VARCHAR(4000)), '^^'))), '000...'))
    # Note: The exact nested order depends on the loop in _build_hash_expression.
    
    print("\nGenerated SQL snippet:")
    print(sql)

if __name__ == "__main__":
    test_hashing_improvements()
