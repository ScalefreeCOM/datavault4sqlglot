from __future__ import annotations
from pydantic import BaseModel, Field

class DataVaultConfig(BaseModel):
    """
    Global configuration for Data Vault 2.0 generation parameters.
    """
    end_of_all_times: str = Field(default="9999-12-31", description="Default value for 'end of all times'.")
    beginning_of_all_times: str = Field(default="0001-01-01", description="Default value for 'beginning of all times'.")
    ldts_alias: str = Field(default="ldts", description="Alias for the load date column.")
    rsrc_alias: str = Field(default="rsrc", description="Alias for the record source column.")
    ledts_alias: str = Field(default="ledts", description="Alias for the load end date column.")
    hash: str = Field(default="MD5", description="Default hash algorithm.")
    default_unknown_rsrc: str = Field(default="SYSTEM", description="Default record source for unknown records.")
    default_error_rsrc: str = Field(default="ERROR", description="Default record source for error records.")
    hashkey_input_case_sensitive: bool = Field(default=False, description="Default case sensitivity for hash keys.")
    hashdiff_input_case_sensitive: bool = Field(default=True, description="Default case sensitivity for hash diffs.")
    use_trim: bool = Field(default=True, description="Default trim behavior for hashing.")
    dialect: str = Field(default="snowflake", description="Target SQL dialect for generation.")

# Global config instance that can be overridden
config = DataVaultConfig()
