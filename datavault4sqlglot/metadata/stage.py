from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from datavault4sqlglot.metadata.source import SourceTable


class StageSource(BaseModel):
    """
    Represents the metadata configuration for a Stage table.
    """
    source_model: Union[str, SourceTable] = Field(..., description="The source table or SourceTable object.")
    
    # Mapping of "Hash Key Name" -> List of "Source Columns"
    hashed_columns: Optional[Dict[str, List[str]]] = Field(
        default=None, 
        description="Dictionary mapping hash key aliases to list of source columns."
    )
    
    # Mapping of "Alias" -> "SQL Expression string"
    derived_columns: Optional[Dict[str, str]] = Field(
        default=None,
        description="Dictionary defining derived columns (Alias -> SQL Expression)."
    )
    
    include_source_columns: bool = Field(
        default=True,
        description="Whether to include all original source columns in the output."
    )
