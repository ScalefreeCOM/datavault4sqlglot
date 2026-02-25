from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceModel(BaseModel):
    """
    Unified metadata model representing a source table and its
    Data Vault staging configuration.

    Combines source identity, business key definitions, hashing configuration,
    and stage-layer enrichment (derived columns, hashed columns) into a single
    object — analogous to a dbt source + stage model.
    """

    model_config = ConfigDict(populate_by_name=True)

    # === Source identity ===
    database: Optional[str] = Field(
        default=None, description="The database name."
    )
    schema_name: Optional[str] = Field(
        default=None, alias="schema", description="The schema name."
    )
    table_name: str = Field(..., description="The table name.")

    # === Business key & metadata columns ===
    business_keys: list[str] = Field(
        default_factory=list,
        description="List of columns to be used as business keys.",
    )
    load_date_col: Optional[str] = Field(
        default=None,
        description="Column name representing the load date/timestamp.",
    )
    record_source_col: Optional[str] = Field(
        default=None,
        description="Column name representing the record source.",
    )

    # === Hash key (for the target entity) ===
    hash_key_col: Optional[str] = Field(
        default=None,
        description="Optional column name representing the hash key.",
    )
    source_columns: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional mapping of source column names to target column aliases.",
    )
    rsrc_statics: Optional[list[str]] = Field(
        default=None,
        description="Optional list of static values for this source (used in multi-source HWM logic).",
    )

    # === Link-specific ===
    link_hash_key: Optional[str] = Field(
        default=None,
        description="The name of the hash key column in the target link.",
    )
    foreign_hash_keys: Optional[list[str]] = Field(
        default=None,
        description="The names of the hash key columns from the hubs in the target link.",
    )

    # === Satellite-specific ===
    hash_diff: Optional[str] = Field(
        default=None,
        description="The name of the hash diff column in the target satellite.",
    )
    payload: Optional[list[str]] = Field(
        default=None,
        description="The names of the descriptive attribute columns.",
    )

    # === Stage-specific enrichment ===
    hashed_columns: Optional[dict[str, list[str]]] = Field(
        default=None,
        description="Dictionary mapping hash key aliases to list of source columns.",
    )
    derived_columns: Optional[dict[str, str]] = Field(
        default=None,
        description="Dictionary defining derived columns (Alias -> SQL Expression).",
    )
    include_source_columns: bool = Field(
        default=True,
        description="Whether to include all original source columns in the output.",
    )


