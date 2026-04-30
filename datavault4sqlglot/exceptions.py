from __future__ import annotations


class GeneratorError(Exception):
    """Raised when a generator cannot produce valid SQL from the given inputs."""


class ConfigurationError(Exception):
    """Raised when the DataVaultConfig contains invalid or missing values."""
