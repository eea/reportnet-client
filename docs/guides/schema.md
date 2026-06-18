# Dataset schema

The `get_schema()` method returns the full table and field definitions for a
dataset. Use it to discover column names, types, and which fields are required
before building an import CSV.

## Retrieve a schema

```python
flow = client.for_dataflow(1619)

schema = flow.get_schema(dataset_id=93953)
# DatasetSchema(id="...", name="...", tables=(...))
```

## Explore tables and fields

```python
for table in schema.tables:
    print(f"\n{table.name}")
    print(f"  required: {table.required_columns()}")
    print(f"  all:      {table.column_names()}")
```

Example output:

```
Table1a
  required: ['category', 'scenario', 'ry', 'cyear', 'gas']
  all:      ['category', 'scenario', 'ry', 'cyear', 'gas', 'cvalue', 'notation', 'inventorySubmissionYear']
```

## Look up a specific table

```python
table = schema.table("Table1a")   # raises KeyError if not found

for field in table.fields:
    print(field.name, field.type, "required" if field.required else "")
```

```
category   FieldType.LINK            required
scenario   FieldType.LINK            required
ry         FieldType.LINK            required
cyear      FieldType.NUMBER_INTEGER  required
gas        FieldType.LINK            required
cvalue     FieldType.NUMBER_DECIMAL
notation   FieldType.LINK
```

## FieldType values

| Value | Meaning |
|-------|---------|
| `TEXT` | Free text |
| `NUMBER_INTEGER` | Whole number |
| `NUMBER_DECIMAL` | Decimal number |
| `DATE` | Date (ISO 8601) |
| `DATETIME` | Date + time |
| `BOOLEAN` | True / False |
| `CODELIST` | Single value from a fixed list |
| `MULTISELECT_CODELIST` | Multiple values from a fixed list |
| `LINK` | Reference to a value in a reference dataset |
| `MULTISELECT_LINK` | Multiple references |
| `ATTACHMENT` | File attachment |

Unknown types pass through as opaque strings so the client doesn't break
when the API adds new types.

## LINK fields — resolving valid values

`LINK` fields store references to a column in a **reference dataset**. Each such field
exposes the source metadata:

```python
for field in table.fields:
    if field.referenced_schema_id:
        print(
            f"{field.name} → "
            f"schema {field.referenced_schema_id}, "
            f"pk field {field.referenced_pk_id}"
        )
# category → schema 68dd410245f9450001260d45, pk field 68dd418645f9450001260d6e
# scenario → schema 68dd410245f9450001260d45, pk field 68dd419a45f9450001260d7a
```

Use `get_codelists()` to export the reference dataset and resolve the valid values
in one call. The result maps field name → sorted list of valid strings:

```python
codelists = flow.get_codelists(dataset_id=93953, ref_dataset_id=REF_DATASET_ID)
# {"category": ["Total excluding LULUCF", "Total including LULUCF"],
#  "scenario": ["WAM", "WEM", "WOM"],
#  "ry": ["0", "1"]}
```

Pass `codelists` to `to_frame()` so LINK columns become `pl.Enum` (polars) or
`CategoricalDtype` (pandas) — invalid values are rejected at assignment time:

```python
frame = table.to_frame(codelists=codelists)
print(frame.schema)
# {'category': Enum(categories=['Total excluding LULUCF', 'Total including LULUCF']),
#  'scenario': Enum(categories=['WAM', 'WEM', 'WOM']),
#  'cyear': Int64, 'cvalue': Float64, ...}
```

## Get an empty DataFrame with correct types

Returns an empty polars (or pandas) DataFrame whose column names and dtypes
match the table schema. Useful for building import data programmatically.

```python
table = schema.table("Table1a")
frame = table.to_frame()
# shape: (0, 8)  — zero rows, correct columns and types
print(frame.schema)
# {'category': String, 'scenario': String, 'ry': String,
#  'cyear': Int64, 'gas': String, 'cvalue': Float64, ...}

# Get all tables at once (optionally with codelists)
frames = schema.to_frames(codelists=codelists)
# {"Table1a": <empty DataFrame with Enum columns>, ...}
```

You can then populate it and pass it straight to `import_file()`:

```python
import polars as pl

empty = schema.table("Table1a").to_frame()
data = pl.concat([empty, pl.DataFrame({
    "category": ["Total including LULUCF"],
    "scenario": ["WEM"],
    "ry": ["0"],
    "cyear": [2024],
    "gas": ["CO2"],
    "cvalue": [1234.5],
    "notation": ["NA"],
    "inventorySubmissionYear": [2024],
})])
ie.import_file(dataset_id=93953, file=data, table_schema_id="68dd41f0...")
```

## Generate a template CSV header

```python
table = schema.table("Table1a")
header = "|".join(table.column_names())   # pipe-delimited
print(header)
# category|scenario|ry|cyear|gas|cvalue|notation|inventorySubmissionYear
```

!!! warning
    Never include a `record_id` column — Reportnet assigns it on ingestion.
