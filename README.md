# datavault4sqlglot

## Configuration

The library uses a global configuration object (`datavault4sqlglot.config`) with sane defaults. 
You can override these defaults by placing a `config.json` file in your current working directory. 
The library will automatically load and apply these settings when imported.

**Example `config.json`:**
```json
{
  "ldts_alias": "load_date_timestamp",
  "hash": "SHA256",
  "dialect": "bigquery"
}
```

You can also manually load a configuration file from a specific path:
```python
from datavault4sqlglot.config import config, load_config
load_config(config, "/path/to/my/custom_config.json")
```