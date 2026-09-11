# Uploading

## The short version

```python
me.import_frames(
    dataset_id=108952,
    frames={"Agglomerations": agglomerations_df, "UWWTPs": plants_df},
    replace=True,
)
```

That uploads each table, waits for each one to finish, and raises if any fails.
`replace=True` clears the table first, so running it twice does not give you
duplicates. Leave it out to add rows instead.

## Your columns will not match, and that is fine

Reportnet rejects an upload whose column headers are not **exactly** the table's
field list. Not a few extra, not a few missing — exactly.

Real data never arrives like that. It carries extra columns from whatever
produced it, it is missing fields your source never had, and dates often come
through with a time attached that a date field refuses.

`import_frames` fixes all of that for you before sending. It adds missing
fields as empty, drops columns the schema does not know, puts them in the right
order, and formats dates. You will see it in the log:

```
WARNING Agglomerations: dropped 6 column(s) not in the schema: ['countryCode', 'snapshotId', ...]
WARNING Agglomerations: added ['repCode'] as EMPTY but the schema marks it required — supply a value
```

**Read those warnings.** The first is usually harmless — pipeline leftovers. The
second is not: it means a required field has no value, which will pass the
upload and fail validation. Only you can supply the value.

If you would rather send your frames untouched, pass `align=False`.

## Uploading a file instead

```python
me.import_file(dataset_id=108952, file="agglomerations.csv").wait()
```

Works with a path, raw bytes, a DataFrame, or a zip of CSVs named after the
tables. CSV and zipped CSV are handled directly. Other formats — Excel, XML —
need a conversion step that the dataflow's administrator sets up, and you pass
its `integration_id`.

`.wait()` matters: without it you have only started the job, not finished it.

## Check what actually arrived

```python
for table, info in me.verify_import(dataset_id=108952).items():
    if info["records"]:
        print(table, info["records"], "rows")
```

Worth doing. An upload can report success and still land fewer rows than you
expected.

## If an upload fails

The error tells you why:

```
JobFailedError: Job 249691 ended with status CANCELED:
  Import files contain incorrect headers. Please ensure the headers in your
  files exactly match the field names of the corresponding tables.
```

The message after the colon is Reportnet's own words. See
[when something goes wrong](troubleshooting.md) for what the common ones mean.

## Next

[Checking your data](validation.md).
