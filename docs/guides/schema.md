# What Reportnet expects

Before you upload anything, it helps to see the shape Reportnet wants.

## Tables and fields

```python
schema = me.get_schema(dataset_id=108952)

for table in schema.tables:
    print(table.name, len(table.fields), "fields")
```

```
ReportPeriod 6 fields
Agglomerations 44 fields
UWWTPs 67 fields
...
```

For one table:

```python
table = schema.table("Agglomerations")

for field in table.fields:
    print(field.name, field.type.value, "required" if field.required else "")
```

Field types are things like `TEXT`, `NUMBER_INTEGER`, `DATE`, and `CODELIST`.

## Required fields

Some fields must have a value. Missing ones will not stop the upload — they fail
later, during validation, which is a slower way to find out:

```python
print(table.required_columns())
```

```
['aggState', 'repCode', 'aggCode', 'aggName', 'aggGenerated', ...]
```

## Code lists

A `CODELIST` or `LINK` field only accepts values from a fixed list. Uploading
anything else is an error.

Reportnet keeps these lists in separate "reference datasets", and a dataflow can
have several. The easiest way to get blank tables with the lists already applied
is `get_template()`, which finds the right reference dataset for you:

```python
template = me.get_template(dataset_id=108952)
frame = template["Agglomerations"]      # empty, correct columns and types
```

Fill that in and upload it — no guessing at column names.

If you know which reference dataset holds the lists, you can ask for the values
directly:

```python
codelists = me.get_codelists(dataset_id=108952, ref_dataset_id=108962)
print(codelists["aggState"])        # ['0', '1', ...]
```

## Check before you upload

If you built your table some other way, compare it against the schema first:

```python
problems = table.validate_frame(my_frame, codelists=codelists)
for p in problems:
    print(p)
```

This is a local check — no network, no waiting. It catches missing required
columns and invalid code-list values, which are the two most common reasons an
upload is rejected.

## Next

[Uploading](import.md).
