# reportnet-client

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

## Installation

```bash
pip install reportnet

# Optional: DataFrame support (polars, pandas, modin — via narwhals)
pip install "reportnet[dataframe]"

# Optional: system keychain storage for API keys
pip install "reportnet[keyring]"
```

## Quick start

```python
from reportnet import ReportnetClient

client = ReportnetClient(api_key="your-api-key")

# Scope to a dataflow and a specific reporter country
flow = client.for_dataflow(1619)
ie = flow.for_provider(42)   # Ireland's provider ID

# Import a CSV
ie.import_file(dataset_id=93953, file="ireland.csv").wait()

# Export to DataFrames
frames = ie.etl_export(dataset_id=93953).to_frames()
```

See [Concepts](concepts.md) for the full Reportnet data model, or jump straight
to a [guide](guides/import.md).

## Secure key storage

Store API keys in the OS keychain (macOS Keychain, Windows Credential Manager, etc.)
so they never appear in source code:

```python
import reportnet

# Save once
reportnet.save_key(dataflow_id=1619, api_key="your-api-key")

# Load at runtime
client = ReportnetClient.from_keyring(dataflow_id=1619)
```
