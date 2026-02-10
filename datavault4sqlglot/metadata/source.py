from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class SourceTable(BaseModel):
    """
    Represents the metadata for a source table used in Data Vault generation.
    """
    name: str = Field(..., description="The name of the source table (e.g. 'raw.orders').")
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
