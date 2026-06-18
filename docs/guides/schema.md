# Dataset schema

The `get_schema()` method returns the full table and field definitions for a
dataset. Use it to discover column names, types, and which fields are required
before building an import CSV.

## Retrieve a schema

```python
df = client.for_dataflow(1619)

schema = df.get_schema(dataset_id=93953)
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

## Generate a template CSV

```python
table = schema.table("Table1a")
header = "|".join(table.column_names())   # pipe-delimited
print(header)
# category|scenario|ry|cyear|gas|cvalue|notation|inventorySubmissionYear
```

!!! warning
    Never include a `record_id` column — Reportnet assigns it on ingestion.
