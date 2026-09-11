# How Reportnet is organised

Five words explain almost everything. You will meet all of them in the guides.

## Dataflow

A reporting obligation — "Urban Waste Water Treatment Directive", "Air Quality".
It says what data is expected, who must send it, and by when.

Every dataflow has a number, visible in its web address. You will use it
constantly:

```python
flow = client.for_dataflow(2003)
```

## Reporter

A country or organisation that submits data to a dataflow. You are one.

Internally Reportnet calls this a *data provider* and gives it a number, but you
can work in country codes and let the library do the translation:

```python
me = flow.find_reporter("FR")
```

## Dataset

Where your rows actually live. You usually have more than one — a dataflow might
keep tabular data in one dataset and map data in another.

Each has a number, and that number is what almost every call needs:

```python
for d in me.get_reporting_datasets():
    print(d.id, d.table_name)
```

## Table and field

A dataset holds tables; a table holds fields (columns). Together they are the
**schema** — the exact shape your data has to be in. Reportnet is strict about
it: see [what Reportnet expects](guides/schema.md).

## Reference dataset

Shared lookup data — the lists of valid codes that everyone in the dataflow uses.
It belongs to no reporter. You normally only read from it, and usually without
noticing, because `get_codelists()` fetches from it for you.

---

## How they fit together

```
Dataflow  (the obligation — 2003)
├── Reporter  (you — France)
│   └── Dataset  (108952 "Descriptive data")
│       └── Table  (Agglomerations)
│           └── Field  (aggName, aggCode, …)
└── Reference dataset  (the code lists, shared by everyone)
```

## Two kinds of user

A **reporter** submits data for one country or organisation.

A **custodian** is the dataflow's administrator *and* its developer. They design
the tables and fields, write the quality rules that check your data, and manage
the shared code lists. When a rule looks wrong, a custodian is who you ask.

This matters more than it sounds, because **your API key is one or the other**,
and a custodian key cannot upload report data. See
[getting started](guides/getting-started.md#the-one-thing-that-confuses-everybody).

## One thing the API cannot do

**Release.** When your data is clean, a person presses *Release* on the Reportnet
website. There is no endpoint for it and this library does not pretend otherwise.
Everything up to that point can be automated.
