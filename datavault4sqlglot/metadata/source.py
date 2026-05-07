from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class SourceModel(BaseModel):
    """
    Physical table reference used as input to DV entity generators (Hub, Link, Sat, …).

    Only describes WHERE to find the data and WHICH columns carry the DV pipe
    standard columns (ldts, rsrc).  All transformation metadata (business keys,
    hash keys, payload, …) lives on the generator or on a SourceBinding.
    """

    model_config = ConfigDict(populate_by_name=True)

    database: Optional[str] = Field(default=None)
    schema_name: Optional[str] = Field(default=None, alias="schema")
    table_name: str = Field(...)

    # None → generator falls back to config.ldts_alias / config.rsrc_alias
    load_date_col: Optional[str] = Field(default=None)
    record_source_col: Optional[str] = Field(default=None)


class StageModel(BaseModel):
    """
    Metadata for a raw source table fed into StageGenerator.

    Extends the physical table reference with all stage-layer concerns:
    hashing, derived columns, and schema evolution.
    """

    model_config = ConfigDict(populate_by_name=True)

    database: Optional[str] = Field(default=None)
    schema_name: Optional[str] = Field(default=None, alias="schema")
    table_name: str = Field(...)

    # Raw column names before aliasing — may differ from DV defaults
    load_date_col: Optional[str] = Field(default=None)
    record_source_col: Optional[str] = Field(default=None)

    # Hash column definitions
    hashed_columns: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = Field(default=None)

    # Derived columns: alias → SQL expression string
    derived_columns: Optional[Dict[str, str]] = Field(default=None)

    # Whether to SELECT * from source (True = include all source columns)
    include_source_columns: bool = Field(default=True)

    # Hashing behaviour overrides
    case_sensitivity: Optional[bool] = Field(default=None)
    use_rtrim: Optional[bool] = Field(default=None)

    # NULL placeholder columns for schema evolution: col_name → SQL datatype
    missing_columns: Optional[Dict[str, str]] = Field(default=None)

    # Column name for a ROW_NUMBER() OVER () sequence expression
    sequence: Optional[str] = Field(default=None)


@dataclass
class SourceBinding:
    """
    Pairs a physical SourceModel with per-source DV loading metadata.

    Used wherever a generator can accept multiple sources (Hub, Link).
    Each binding describes what the generator should extract from that
    particular staging table.

    Attributes:
        source:            Physical table reference.
        bk_columns:        Per-source physical business-key columns. They map
                           positionally to the hub-level ``business_keys``.
                           When omitted, the source is assumed to already use
                           the canonical names declared on ``HubGenerator``.
        fk_columns:        Per-source physical foreign-hash-key columns. They
                           map positionally to the link-level
                           ``foreign_hash_keys``. When omitted, the source is
                           assumed to already use the canonical names declared
                           on ``LinkGenerator``.
        hash_key_col:      Source column carrying the entity's hash key.
                           Defaults to the generator's own hash-key parameter.
        payload:           Source columns to carry as satellite / NHLink payload.
        rsrc_statics:      LIKE-pattern strings for HWM scoping per source system.
        additional_columns: Extra columns to carry through all CTEs.
    """

    source: SourceModel
    bk_columns: Optional[list[str]] = None
    fk_columns: Optional[list[str]] = None
    hash_key_col: Optional[str] = None
    payload: list[str] = field(default_factory=list)
    rsrc_statics: Optional[list[str]] = None
    additional_columns: Optional[list[str]] = None
