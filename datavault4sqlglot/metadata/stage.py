from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datavault4sqlglot.metadata.source import SourceTable

class StageSource(BaseModel):
    """
    Represents the metadata configuration for a Stage table.
    """
    database: Optional[str] = Field(default=None, description="The source database name.")
    schema_name: Optional[str] = Field(default=None, alias="schema", description="The source schema name.")
    table_name: Optional[str] = Field(default=None, description="The source table name.")
    source_model: Optional[SourceTable] = Field(default=None, description="A SourceTable object if granular source metadata is already defined.")
    
    hashed_columns: Optional[Dict[str, List[str]]] = Field(
        default=None, 
        description="Dictionary mapping hash key aliases to list of source columns."
    )
    derived_columns: Optional[Dict[str, str]] = Field(
        default=None,
        description="Dictionary defining derived columns (Alias -> SQL Expression)."
    )
    include_source_columns: bool = Field(
        default=True,
        description="Whether to include all original source columns in the output."
    )

    class Config:
        populate_by_name = True
