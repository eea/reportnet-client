# Code Review — reportnet-client

Scope: `src/reportnet/*` and `notebooks/*.py` (plus the tests that exercise them),
reviewed against the actual code, the unit test suite, `mypy`/`ruff` output, and
the last CI run on `main`. No files were changed as part of this review.

**Note on stack assumptions.** The review request mentioned Polars / SQLModel /
Pydantic and a database layer. The actual stack is different: DataFrames are
handled via **narwhals** (backend-agnostic over polars/pandas/modin), models are
plain **frozen dataclasses** (`models.py`), and there is **no ORM, no SQLModel,
no Pydantic, and no database** — this is a REST API client only. The review
below is grounded in what's actually in the repo.

---

## 1. Architecture & design

Overall the module layout is coherent and the public/internal split is clean:
`_http.py` and `_util.py` are underscore-prefixed and never re-exported;
`client.py`, `dataflow.py`, `models.py`, `exceptions.py`, `providers.py`,
`keychain.py` are public and fully re-exported through `__init__.py`. There's
no accidental circular-import breakage (`import reportnet` works standalone),
and the apparent `client.py` ↔ `dataflow.py` cycle is deliberately broken with
`TYPE_CHECKING` guards + function-local imports. Most other function-local
imports (`from .keychain import get_key`, `from ._util import build_codelists`,
`import geopandas as gpd`, …) exist to keep optional extras
(`[dataframe]`/`[keyring]`/`[spatial]`) lazy — `import reportnet` shouldn't
require `keyring` or `geopandas` to be installed. That's a good, intentional
pattern, just undocumented as such (see nitpick N1).

**[Important] Inconsistent `etl_export` version auto-detection between the two client layers**
`src/reportnet/dataflow.py:301-343` vs `src/reportnet/client.py:215-243`

`DataflowClient.etl_export()` defaults `version=None` and auto-picks 3 vs 4 via
`is_big_dataflow()`. The lower-level `ReportnetClient.etl_export()` — the layer
CLAUDE.md describes as "one method per API operation" and that `docs/api/client.md`
documents directly — always defaults to `version=4`:

```python
# client.py:215-224
def etl_export(
    self,
    *,
    dataset_id: int,
    dataflow_id: int,
    ...
    version: int = 4,
) -> JobHandle:
```

A caller who uses `ReportnetClient` directly (bypassing `DataflowClient`) on a
Citus dataflow and forgets `version=3` silently hits the BigData endpoint and
gets a ZIP-of-CSV response parsed as if... actually the opposite failure mode:
v3 returns JSON-in-ZIP, v4 returns CSV-in-ZIP, and `zip_to_frames()` (`_util.py:110-121`)
branches on file extension, so the wrong version mostly "works" but silently
returns the wrong shape/columns for the dataset's actual backend. This is a
plausible design choice (auto-detection needs a `dataflow_id`-scoped
`is_big_dataflow()` call, which `DataflowClient` has cheaply and `ReportnetClient`
does too, just not automatically) — **asking rather than assuming**: should
`ReportnetClient.etl_export()` also auto-detect when `version` is left as a
sentinel (`None`), for symmetry with `DataflowClient`?

---

## 2. Correctness

**[Critical] CI is currently red on `main` — two `ruff` errors and one `mypy` error are already committed**

Verified via `uv run ruff check src tests`, `uv run mypy src`, and
`gh run view` on the most recent "Tests" workflow run on `main` (the merge of
this very branch, run `28522074220`), which fails at the lint step:

```
##[group]Run uv run ruff check src tests
Found 2 errors.
##[error]Process completed with exit code 1.
```

Errors, both reproducible locally:

1. `src/reportnet/_util.py:405-406` — `I001` unsorted import block:
   ```python
   import json as _json
   from shapely.geometry import shape as _shape
   ```
   Fix (matches `ruff --fix`'s own suggestion — separate the stdlib and
   third-party groups with a blank line):
   ```python
   import json as _json

   from shapely.geometry import shape as _shape
   ```

2. `src/reportnet/client.py:65` — `E501` line too long (101 > 100):
   ```python
   return cls(api_key=get_key(dataflow_id, sandbox=sandbox), base_url=base_url, timeout=timeout)
   ```
   Fix:
   ```python
   return cls(
       api_key=get_key(dataflow_id, sandbox=sandbox),
       base_url=base_url,
       timeout=timeout,
   )
   ```

3. `mypy src` separately fails (independent of ruff, would surface once lint
   is fixed): `src/reportnet/_util.py:406: error: Library stubs not installed
   for "shapely.geometry" [import-untyped]`. The sibling `geopandas` import
   three lines above already carries the ignore comment:
   ```python
   # _util.py:383
   import geopandas as gpd  # type: ignore[import-untyped]
   ```
   but the `shapely.geometry` import added later does not:
   ```python
   # _util.py:406
   from shapely.geometry import shape as _shape
   ```
   Fix: add the same pragma, for consistency with how the rest of the file
   handles untyped optional dependencies:
   ```python
   from shapely.geometry import shape as _shape  # type: ignore[import-untyped]
   ```

---

**[Important] Wrapped-401-as-500 detection is implemented twice, with two different (non-equivalent) patterns**
`src/reportnet/_http.py:54` vs `src/reportnet/_http.py:90-93`

The retry loop's "don't waste attempts on a bad API key" check only matches
one substring:

```python
# _http.py:54
is_auth_500 = r.status_code == 500 and "UNAUTHORIZED" in r.text
```

but the exception-raising check a few lines later matches three:

```python
# _http.py:90-93
if response.status_code == 500 and (
    "UNAUTHORIZED" in body or '"401"' in body or "'401'" in body
):
    raise AuthError(response.status_code, body)
```

A wrapped-401 response whose body contains `"401"` (or `'401'`) but not the
literal string `UNAUTHORIZED` will **not** be recognized by `is_auth_500`, so
`_request()` retries it up to 3 times with exponential backoff (~1s, ~2s, ~4s)
on GET requests before `_raise_for_status()` finally raises `AuthError` — the
comment above `_raise_for_status` explicitly says this detection exists "so
the retry loop does not waste attempts on a bad API key," but the two checks
have drifted apart. `test_500_wrapping_401_is_not_retried` in
`tests/test_http_retry.py:113` only exercises the `"UNAUTHORIZED"` case, so
this gap isn't caught by the test suite.

Fix — extract one shared predicate and use it in both places:

```python
def _is_wrapped_auth_500(response: httpx.Response) -> bool:
    if response.status_code != 500:
        return False
    body = response.text
    return "UNAUTHORIZED" in body or '"401"' in body or "'401'" in body
```

```python
# in _request():
is_auth_500 = _is_wrapped_auth_500(r)
...
# in _raise_for_status():
if _is_wrapped_auth_500(response):
    raise AuthError(response.status_code, response.text)
```

---

**[Important] `_etl_json_to_frames` produces a phantom 1-row frame for empty tables**
`src/reportnet/_util.py:130-152`

```python
rows = [...]
result[name] = records_to_frame(rows) if rows else records_to_frame([{}])
```

For a table with zero records, this calls `records_to_frame([{}])` instead of
building an empty frame. Verified directly:

```
>>> import polars as pl
>>> pl.DataFrame([{}]).shape
(1, 0)
```

So a Citus (v3) export of an empty table comes back as **1 row × 0 columns**
instead of **0 rows**. Anything downstream that checks `frame.shape[0] == 0`
to mean "no data" (e.g. the pattern used throughout `tests/test_integration.py`,
such as `test_cast_frame_with_real_export`'s `if raw_frame.shape[0] == 0: ...
skip`) will misbehave for Citus exports specifically, and row-count summaries
like the one in `notebooks/02_import_export_pipeline.py:389-395`
(`f"- **{name}**: {f.shape[0]} rows × {f.shape[1]} cols"`) will report "1 rows
× 0 cols" for an empty table instead of "0 rows".

This path has **zero test coverage** — no test in `tests/` references
`_etl_json_to_frames`, `_records_to_frame`, or exercises the JSON-branch of
`zip_to_frames()` at all (only the CSV/v4 branch is tested, in
`tests/test_exports.py`).

Fix:
```python
for table in data.get("tables", []):
    name: str = table["tableName"]
    rows = [
        {f["fieldName"]: f["value"] for f in rec.get("fields", [])}
        for rec in table.get("records", [])
    ]
    result[name] = records_to_frame(rows)
```
This requires `records_to_frame([])` to work for both backends — verify (or
special-case) that `pl.DataFrame([])` / `pd.DataFrame([])` return a genuine
0-row, 0-column frame rather than raising; if a fully-typed empty frame is
needed here, reuse `table_to_frame()` from the corresponding `TableSchema`
instead of inferring an empty schema from zero rows.

---

**[Important] Stale/broken assertion in the only test that exercises `to_mermaid()`**
`tests/test_integration.py:562-567` vs `src/reportnet/dataflow.py:683-789`

```python
@pytest.mark.integration
def test_to_mermaid(df_1619):
    mmd = df_1619.to_mermaid()
    assert mmd.startswith("graph LR")
    assert 'df[["' in mmd                  # dataflow node
    assert "subgraph cluster_" in mmd      # at least one reporter cluster
```

`to_mermaid()`'s current implementation never emits a `subgraph` — confirmed
by grepping the whole repo: the string `subgraph`/`cluster_` appears **only**
in this one assertion. The implementation instead emits one flat node per
provider (`p_{provider_id}`, dataflow.py:764-787). This test would fail if
anyone actually ran it — but since integration tests are `pytest.mark.skip`'d
by default (`conftest.py:16-23`) and aren't part of CI (`tests.yml` runs
`pytest -v` with no `--integration`), nobody would notice. This is the most
concrete evidence in the repo that "risky and untested" code (§5) is a real,
not theoretical, problem: `to_mermaid()` apparently lost its per-country
subgraph clustering at some point and the only test that would have caught it
never runs.

Fix: either restore subgraph clustering if it was an intentional feature, or
(more likely, given the current flat-node design looks deliberate) update the
assertion to match reality and — more importantly — add this as a **unit**
test (feeding synthetic `get_dataflow`/`get_reporters`/`get_reporting_datasets`
responses through `mock_router`, same pattern as the rest of `tests/`) so it
runs in normal CI instead of only under `--integration`.

---

## 3. Data handling (narwhals / polars / pandas)

The narwhals abstraction is used consistently and correctly — `eager_only=True`
throughout means there's no lazy-frame confusion to worry about, and the
polars-first/pandas-fallback pattern (`table_to_frame`, `ValidationResult.to_frame`,
`zip_to_frames`) is applied uniformly. A few smaller observations:

**[Nitpick] `FieldType._missing_` creates non-singleton enum-like instances**
`src/reportnet/models.py:181-187`

```python
@classmethod
def _missing_(cls, value: object) -> "FieldType":
    # Pass unknown types through as opaque strings rather than raising.
    unknown = str.__new__(cls, str(value))
    unknown._value_ = str(value)
    unknown._name_ = str(value)
    return unknown
```

Verified:
```
>>> FieldType('FUTURE_TYPE') is FieldType('FUTURE_TYPE')
False
>>> FieldType('FUTURE_TYPE') == FieldType('FUTURE_TYPE')
True
```
Nothing in the codebase currently compares `FieldType` by identity or does
`x in list(FieldType)`-style membership checks, so this is harmless today.
Flagging because it's an unusual pattern (constructing new, unregistered enum
members outside `_member_map_` on every call) that would silently break if
someone later added an identity check or iterated `FieldType` expecting all
seen values to appear. If this is intentional (I'd guess it is, per the
comment), a one-line docstring note on the class would save the next reader
from re-deriving this.

**[Nitpick] Inconsistent required-vs-defaulted field parsing in `models.py`**
`src/reportnet/models.py:96` vs the rest of the file

```python
# ReportingDataset.from_dict, models.py:91-100
provider_id=int(d["dataProviderId"]),   # raises KeyError if missing
```
Every other `from_dict` in the file (`DataflowInfo`, `Reporter`,
`ReferenceDataset`, `TestDataset`, `FieldSchema`) uses `.get(..., default)` or
`.get(...) or default` defensively, including `Reporter.provider_id` two
classes above it (`d.get("dataProviderId", 0)`, line 58) — the same field
name, different treatment. If `dataProviderId` really is guaranteed present
on `reportingDatasets` entries, a short comment would make the asymmetry
intentional rather than looking like an oversight.

---

## 4. Marimo notebooks

The reactivity discipline is good — every notebook correctly gates
side-effecting cells behind `mo.stop(...)`, and cross-cell variable references
are used exclusively (no hidden globals I could find), so cells should
re-order correctly under marimo's dependency graph. The issues found are
narrower:

**[Important] Duplicated "Connect" boilerplate across all three notebooks, already drifting**
`notebooks/01_explore_dataflow.py:40-107`, `notebooks/02_import_export_pipeline.py:45-119`, `notebooks/03_spatial_geodataframe.py:48-123`

The same ~65-line pattern — dataflow ID input, sandbox checkbox, API-key-save
accordion, then a `try/except KeyError/ValueError/AuthError` connect block —
is copy-pasted three times with cosmetic renames (`key_input` vs `key_input_02`,
`_rn` vs `_rn02`, etc.). It has already drifted: notebook 01 has no
`except ValueError` branch (it doesn't call `find_reporter`), notebooks 02/03
do. This is exactly the kind of logic the task asked to identify as
"should live in the library instead of notebooks." Suggested fix — a small
helper in the library (or a `notebooks/_shared.py` imported by all three,
since marimo notebooks can import local modules) that returns
`(flow_or_None, ok: bool, message: mo.Html)`, e.g.:

```python
# reportnet, new helper (illustrative signature)
def connect_interactive(dataflow_id: int, *, sandbox: bool = False,
                         country_code: str | None = None) -> ConnectResult:
    """Try from_keyring() -> for_dataflow() -> (optional) find_reporter(),
    returning a uniform (flow, ok, message) result for UI callers."""
```
so each notebook's connect cell shrinks to a couple of lines and the three
copies can't drift again.

**[Important] Notebook clients are never closed — reactive re-runs leak a fresh connection pool each time**
`notebooks/01_explore_dataflow.py:82`, `notebooks/02_import_export_pipeline.py:91`, `notebooks/03_spatial_geodataframe.py:96`

```python
_client = reportnet.ReportnetClient.from_keyring(_did, sandbox=_sandbox)
_flow = _client.for_dataflow(_did)
```

`ReportnetClient` wraps a pooled `httpx.Client` and supports `with` (
`client.py:155-159`: `__enter__`/`__exit__` calling `close()`), but none of the
notebooks use it. Because this cell reruns on every edit to the Dataflow ID
input, the Sandbox checkbox, or (in 02/03) the country-code field, each edit
silently constructs a new `httpx.Client`/connection pool and abandons the
previous one without closing it. For a single edit this is negligible; for an
interactive session where someone is trying several dataflow IDs it accumulates
unclosed sockets. Fix — at minimum wrap in `with`, or explicitly close the
old client. In marimo this is easiest via a small context object stored across
reruns, or simply documenting/accepting it if the maintainers consider this
an acceptable tradeoff for notebook ergonomics (worth asking, since explicit
cleanup in a reactive cell is genuinely awkward with marimo's model).

**[Nitpick] Notebook 01 raises `AuthError` with the dataflow ID as the HTTP status code**
`notebooks/01_explore_dataflow.py:88`

```python
if not _flow.ping():
    raise reportnet.AuthError(_did, "API key invalid or revoked")
```

`AuthError.__init__(self, status_code: int, response_body: str)` — here `_did`
(the *dataflow ID*, e.g. `1570`) is passed as `status_code`. It works today
only because the exception is immediately caught by the very next
`except reportnet.AuthError:` clause and its attributes are never inspected.
But `exc.status_code` now holds `1570` instead of `401`, and `str(exc)` would
render `"HTTP 1570: API key invalid or revoked"` — misleading if this ever
gets logged or the except-branch is changed to print `exc`. Fix:
```python
raise reportnet.AuthError(401, "API key invalid or revoked")
```

**[Nitpick] Stray literal in a UI label**
`notebooks/01_explore_dataflow.py:42`

```python
dataflow_id_input = mo.ui.number(value=1570, label="1570", step=1)
```
Compare notebook 02 (`label="Dataflow ID"`, line 47) and notebook 03
(`label="Dataflow ID"`, line 50) — notebook 01's label is a stray copy of the
`value=1570` literal instead of a real label. The rendered control shows
"1570" as its caption rather than "Dataflow ID". Fix:
```python
dataflow_id_input = mo.ui.number(value=1570, label="Dataflow ID", step=1)
```

No hardcoded credentials were found in any notebook (API keys are always
sourced from the keychain or a password-masked `mo.ui.text`); the hardcoded
defaults present (`dataflow_id=1570`/`1619`, `country_code="IE"`/`"FR"`) are
clearly example values exposed as editable UI controls, not baked-in
constants, so they don't need parameterizing further.

---

## 5. Consistency & maintainability

**[Important] Zero unit-test coverage for several non-trivial, risky functions**

Grepping `tests/` (excluding the skip-by-default `test_integration.py`) for
each of the following turns up nothing:

| Function | Why it's risky |
|---|---|
| `DataflowClient.to_mermaid()` (`dataflow.py:683`) | String-building with escaping, status-priority ranking, grouping — already found to be stale/broken above (§2) |
| `ValidationResult._from_raw()` (`models.py:499-543`) | Parses server JSON with fallback keys (`errors` vs `validations`), string→int coercion of `numberOfRecords`, several `or None`/`or ""` branches — exactly the kind of code that breaks quietly on a slightly different API response shape |
| `DataflowClient.validate()` (`dataflow.py:429-475`) | Chains three calls (`add_validation_job` → `wait` → `list_group_validations_dl`) into one public API |
| `get_codelists()` / `get_template()` (`dataflow.py:502-623`) | Multi-step orchestration with a broad `except ReportnetError: pass` fallback (`dataflow.py:615-621`) — worth a test confirming the fallback actually produces plain-string columns |
| `import_frames()` (`dataflow.py:221-283`) | Loops and raises `ValueError` on table-name mismatches |
| `keychain.py` (`save_key`/`get_key`/`delete_key`) | Entirely untested; could at least be tested with `keyring`'s in-memory test backend rather than the real OS keychain |
| `to_geodataframe()`'s GeoJSON branch (`_util.py:401-419`) | Only the WKT branch is unit-tested (`tests/test_imports.py:132-150`); the `first_valid.lstrip().startswith("{")` GeoJSON-detection branch has no test at all |

This matters more than a generic "add more tests" note: the `to_mermaid()`
finding in §2 is a live example of exactly this gap causing an undetected
regression. I'd prioritize `ValidationResult._from_raw()` and the GeoJSON
branch next, since both parse untrusted external data with several silent
fallbacks (`or None`, `or ""`, bare `except Exception: pass` at
`_util.py:395` and `_util.py:415`) that are easy to get subtly wrong.

**[Important] CLAUDE.md's documented architecture has drifted from the code**

`CLAUDE.md`'s "Exception hierarchy" section omits `DatasetLockedError`
(HTTP 423, added and used throughout — `_http.py:80-81`, `client.py`,
tested in `test_http_retry.py:93-101`). Its module/API map has no mention of
the schema layer (`DatasetSchema`/`TableSchema`/`FieldSchema`/`FieldType` and
their `validate_frame`/`cast_frame`/`to_frame` methods), `ValidationResult`/
`ValidationIssue`, spatial/geopandas support (`to_geodataframe`, the
`[spatial]` extra), `providers.py`'s `by_id`/`by_country`/`by_group`, or the
higher-level `DataflowClient` convenience methods (`get_template`,
`get_codelists`, `import_frames`, `validate`, `to_mermaid`, `find_reporter`) —
all of which are current, tested, public API. Since this file is the primary
context loaded for every Claude Code session in this repo, keeping it in sync
directly affects the quality of future AI-assisted changes here. Given the
size of the drift, this looks like it just hasn't been revisited since an
early version of the library (the CLAUDE.md testing section still only lists
`test_imports.py` / `test_exports.py` / `test_validations.py` / `test_jobs.py`
/ `test_providers.py` / `test_dataflow_client.py` / `test_http_retry.py` —
missing `test_dataflow.py`, `test_schema.py`, `test_notebooks.py`, and
`test_integration.py`, all of which exist and are exercised above).

**[Nitpick] No comment marks intentionally-deferred imports as intentional**
e.g. `src/reportnet/client.py:62,74,89,143`

Function-local imports like `from .keychain import get_key` (inside
`from_keyring`) or `from .dataflow import DataflowClient` (inside
`for_dataflow`) are good design (§1) but undocumented as such. A future
contributor "cleaning up" by hoisting these to the top of the file would
either reintroduce the `client.py`↔`dataflow.py` circular import or force
`import reportnet` to hard-require `keyring`. A one-line comment at each site
(`# deferred: avoids circular import with dataflow.py` /
`# deferred: keep keyring optional`) would prevent that.

**[Nitpick] Retry policy is GET-only; worth confirming DELETE/idempotent-PUT are deliberately excluded**
`src/reportnet/_http.py:55-63`

5xx is only retried for GET, with the stated rationale "POST/PUT may have
side effects" (`_http.py:52`). `set_reference_dataset_updatable` (PUT, toggles
a boolean) and `delete_dataset_data`/`delete_table_data` (DELETE) look
idempotent by nature — asking rather than assuming this is a gap: is the
blanket GET-only policy deliberate conservatism for a production reporting
system (safer default, err on the side of not retrying), or would the
maintainers want idempotent PUT/DELETE endpoints retried too?

---

## Summary — top 5 to fix first

1. **Unbreak CI.** Two `ruff` violations (`_util.py:405` import order,
   `client.py:65` line length) and one `mypy` violation (`_util.py:406`
   missing `type: ignore[import-untyped]` on the `shapely.geometry` import)
   are already committed on `main` and are why the last "Tests" workflow run
   failed. All three fixes are one line each (§2).

2. **Fix the wrapped-401 retry/detection split-brain in `_http.py`.** Extract
   one `_is_wrapped_auth_500()` helper and use it in both the retry-skip
   check (line 54) and the exception-raising check (lines 90-93) so a
   wrapped-401 response can't get needlessly retried before it's correctly
   classified (§2).

3. **Fix the empty-table bug in `_etl_json_to_frames`** (`_util.py:151`,
   `records_to_frame([{}])` → phantom 1-row frame instead of 0 rows) and add
   unit tests for the v3/Citus JSON export path, which currently has none
   (§2, §5).

4. **Reconcile `to_mermaid()` and its only test.** Either restore the
   `subgraph cluster_` output the integration test expects, or update the
   assertion — and either way, add a `mock_router`-based unit test so this
   class of regression is caught by normal CI, not just an opt-in
   `--integration` run nobody triggers (§2, §5).

5. **De-duplicate the notebooks' "Connect" cell** into one shared helper
   (it's already drifted between notebook 01 and notebooks 02/03), and fix
   the two concrete bugs inside it while there: the wrong-type `AuthError`
   construction in notebook 01 (`AuthError(_did, ...)` should be
   `AuthError(401, ...)`) and the stray `label="1570"` (§4).
