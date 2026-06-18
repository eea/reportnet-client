# Concepts

## The Reportnet hierarchy

Reportnet 3 organises data in a three-level hierarchy:

```
Dataflow
  └── Reporter / DataProvider  (a country or organisation)
        └── Dataset  (the data store for that reporter)
              └── Table
                    └── Field (column)
  └── Reference Dataset  (shared lookup data, no reporter)
```

### Dataflow

A **Dataflow** represents a reporting obligation — for example, the
"EU Greenhouse Gas Inventory" or "Air Quality e-Reporting". It defines:

- what tables and fields are expected (the schema)
- which countries or organisations must report (the reporters)
- deadlines and release schedules

Each dataflow has a numeric ID visible in the Reportnet URL.

### Reporter / DataProvider

A **Reporter** (also called a DataProvider) is a country or organisation
that submits data to a dataflow. Each reporter has a numeric `provider_id`.
You can look up provider IDs by country code using the [provider helpers](guides/providers.md).

### Dataset

Each reporter has one **Dataset** per dataflow. This is where their actual
data rows live. A dataset contains one or more tables, each matching the
schema defined by the dataflow.

### Reference Dataset

A **Reference Dataset** is a special dataset shared across all reporters in
a dataflow. It typically contains codelists and lookup values (e.g. gas types,
notation keys). Reference datasets are managed by the dataflow custodian and
have no `provider_id`.

## Client hierarchy

The library mirrors this structure:

```python
# Top-level client — one per API key
client = ReportnetClient(api_key="...")

# Dataflow-scoped client — pre-fills dataflow_id
df = client.for_dataflow(1619)
df.get_dataflow()    # DataflowInfo: name, type, status
df.get_reporters()   # list of Reporter objects with provider_id and dataset_id

# Reporter-scoped client — pre-fills dataflow_id + provider_id
ie = df.for_provider(42)
ie.import_file(dataset_id=93953, file="data.csv")
```

`for_provider()` returns a new `DataflowClient` with the `provider_id` set.
All import, export, and validation calls on it automatically include that ID.

## Sync vs async operations

Some API operations complete synchronously (schema lookup, validation results).
Most data operations — imports, exports, validation jobs — are **asynchronous**:
the API accepts the request and returns a **job ID**, then processes it in the background.

The library wraps these in a [`JobHandle`][reportnet.JobHandle]:

```python
handle = ie.import_file(dataset_id=93953, file="data.csv")
# handle is a JobHandle — the import is running in the background

handle.wait()  # blocks until done; raises JobFailedError on failure
```

## BigData vs Citus

Reportnet has two storage backends:

| Backend | Description | Endpoints |
|---------|-------------|-----------|
| **Citus** | Standard PostgreSQL-based storage | `etl_export`, `etl_import`, `list_group_validations` |
| **BigData (DLT2)** | Large-scale columnar storage | `export_file_dl`, `export_dataset_file_dl`, `list_group_validations_dl` |

Use `df.is_big_dataflow()` to check which backend a dataflow uses and pick
the right methods.
