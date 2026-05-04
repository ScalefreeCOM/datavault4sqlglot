from __future__ import annotations
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field

class DataVaultConfig(BaseModel):
    """
    Global configuration for Data Vault 2 generation parameters.
    """
    end_of_all_times: str = Field(default="9999-12-31", description="Default value for 'end of all times'.")
    beginning_of_all_times: str = Field(default="0001-01-01", description="Default value for 'beginning of all times'.")
    ldts_alias: str = Field(default="ldts", description="Alias for the load date column.")
    rsrc_alias: str = Field(default="rsrc", description="Alias for the record source column.")
    ledts_alias: str = Field(default="ledts", description="Alias for the load end date column.")
    hash: str = Field(default="MD5", description="Default hash algorithm.")
    hashkey_input_case_sensitive: bool = Field(default=False, description="Default case sensitivity for hash keys.")
    hashdiff_input_case_sensitive: bool = Field(default=False, description="Default case sensitivity for hash diffs. False = apply UPPER (case-insensitive), True = preserve case.")
    use_trim: bool = Field(default=True, description="Default trim behavior for hashing.")
    dialect: str = Field(default="snowflake", description="Target SQL dialect for generation.")
    quote_identifiers: bool = Field(default=True, description="Whether to quote table, schema, database, and column identifiers.")

    def update_from_dict(self, data: dict):
        """Update configuration attributes from a dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                logging.warning(f"Configuration key '{key}' is not a valid DataVaultConfig attribute and will be ignored.")

def load_config(config_instance: DataVaultConfig, config_path: str | Path | None = None) -> None:
    """
    Load configuration from a JSON file and update the given config instance.
    If config_path is None, it defaults to 'config.json' in the current working directory.
    """
    if config_path is None:
        config_path = Path.cwd() / "config.json"
    else:
        config_path = Path(config_path)

    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config_instance.update_from_dict(data)
            logging.info(f"Loaded configuration from {config_path}")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse configuration file {config_path}: {e}")
        except Exception as e:
            logging.error(f"Error loading configuration from {config_path}: {e}")

# Global config instance that can be overridden
config = DataVaultConfig()

# Automatically attempt to load config.json from the current working directory
load_config(config)
