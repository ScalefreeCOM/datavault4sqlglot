from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field

class SourceTable(BaseModel):
    """
    Represents the metadata for a source table used in Data Vault generation.
    """
    database: Optional[str] = Field(default=None, description="The database name.")
    schema_name: Optional[str] = Field(default=None, alias="schema", description="The schema name.")
    table_name: str = Field(..., description="The table name.")
    
    business_keys: List[str] = Field(..., description="List of columns to be used as business keys.")
    load_date_col: str = Field(..., description="Column name representing the load date/timestamp.")
    record_source_col: str = Field(..., description="Column name representing the record source.")
    
    hash_key_col: Optional[str] = Field(
        default=None,
        description="Optional column name representing the hash key."
    )
    source_columns: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional mapping of source column names to target column aliases."
    )
    rsrc_statics: Optional[List[str]] = Field(
        default=None,
        description="Optional list of static values for this source (used in multi-source HWM logic)."
    )
    
    # Link specific
    link_hash_key: Optional[str] = Field(
        default=None,
        description="The name of the hash key column in the target link."
    )
    foreign_hash_keys: Optional[List[str]] = Field(
        default=None,
        description="The names of the hash key columns from the hubs in the target link."
    )
    
    # Satellite specific
    hash_diff: Optional[str] = Field(
        default=None,
        description="The name of the hash diff column in the target satellite."
    )
    payload: Optional[List[str]] = Field(
        default=None,
        description="The names of the descriptive attribute columns."
    )

    class Config:
        populate_by_name = True
