from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ExportVerification, ReadbackVerification


class ReportnetError(Exception):
    pass


class APIError(ReportnetError):
    def __init__(self, status_code: int, response_body: str) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"HTTP {status_code}: {response_body}")


class AuthError(APIError):
    pass


class RateLimitError(APIError):
    """Raised on HTTP 429 Too Many Requests."""
    pass


class DatasetLockedError(APIError):
    """Raised on HTTP 423 Locked — another job is already running on this dataset."""
    pass


class DiscoveryNotPermittedError(AuthError):
    """Raised when a key may not read the dataflow needed to look something up.

    A Reporter key can import into and validate its own datasets, but is
    forbidden from ``GET /dataflow/v1/{id}`` — the only endpoint that lists
    dataset IDs. Everything that resolves a *name* to an *id* therefore fails
    for the role that most needs it.

    Subclasses :class:`AuthError`, so existing ``except AuthError`` handlers
    still catch it. It exists to carry an actionable message instead of a bare
    ``HTTP 403``.
    """


class CodelistResolutionError(ReportnetError):
    """Raised when LINK/CODELIST fields could not be resolved to valid values.

    Only raised when ``strict=True`` is passed to
    :meth:`~reportnet.DataflowClient.get_codelists` or
    :meth:`~reportnet.DataflowClient.get_template`. By default, unresolved
    fields are logged and warned about, and the affected columns fall back to
    plain strings.

    Attributes:
        unresolved: Names of the fields that could not be resolved.
    """

    def __init__(self, unresolved: list[str], detail: str = "") -> None:
        self.unresolved = unresolved
        message = (
            f"Could not resolve valid values for {len(unresolved)} field(s): "
            f"{sorted(unresolved)}"
        )
        super().__init__(f"{message}. {detail}".strip())


class DataflowNotPublicError(ReportnetError):
    """A dataflow's schema was requested publicly, but it is not published.

    ``downloadPublicSchemaInformation`` serves published dataflows only, and
    answers 404 for anything else — including a private test copy of a dataflow
    that *is* public. There is no API-key route to the same file, so a private
    dataflow's rules have to be exported from the web UI by hand.
    """

    def __init__(self, dataflow_id: int) -> None:
        self.dataflow_id = dataflow_id
        super().__init__(
            f"Dataflow {dataflow_id} is not public, so its schema is not served here. "
            f"Export it from the Reportnet web UI instead."
        )


class JobFailedError(ReportnetError):
    """A job reached a terminal non-successful status.

    ``info`` carries Reportnet's own explanation from the poll response, when
    it gave one. It is the only place the real reason appears — the status
    alone is never actionable. Live examples: "Import files contain incorrect
    headers. Please ensure the headers in your files exactly match the field
    names of the corresponding tables." and "Import is not allowed for this
    dataset." (a locked reference dataset).
    """

    def __init__(self, job_id: int, status: str, info: str | None = None) -> None:
        self.job_id = job_id
        self.status = status
        self.info = info
        message = f"Job {job_id} ended with status {status}"
        if info:
            message += f": {info}"
        super().__init__(message)


class JobTimeoutError(ReportnetError):
    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"Timed out waiting for job {job_id}")


class ExportVerificationError(ReportnetError):
    """An export did not match the requested schema; inspect ``verification``."""

    def __init__(self, verification: "ExportVerification") -> None:
        self.verification = verification
        super().__init__(verification.summary())


class ReadbackVerificationError(ReportnetError):
    """Uploaded data did not match readback. Writes may already have completed."""

    def __init__(self, verification: "ReadbackVerification") -> None:
        self.verification = verification
        super().__init__(verification.summary() + "; validation was not started. "
                         "Inspect current data before retrying; uploads are not rolled back.")


class SchemaDesignNotPermittedError(AuthError):
    """Schema design was attempted with an API key.

    Raised **before** any request is sent. API keys get 403 on every schema
    write and on ``getSchemas``; a login token is needed (verified on sandbox
    dataflow 11468, 2026-11-12). Create the client with
    :meth:`~reportnet.ReportnetClient.from_tokens`.
    """

    def __init__(self, operation: str) -> None:
        super().__init__(
            403,
            f"{operation} needs a login token, not an API key: API keys get 403 on "
            "schema changes (verified on the sandbox, 2026-11-12). Create the client "
            "with ReportnetClient.from_tokens(access_token, refresh_token).",
        )


class SchemaWriteUncertainError(APIError):
    """A schema change got a server error. **It may still have been applied.**

    Seen live: a field update answered HTTP 500 and the new description was
    saved anyway. Read the schema again before you retry.
    """

    def __init__(self, status_code: int, response_body: str, operation: str) -> None:
        self.operation = operation
        if "Load balancer does not have available server" in response_body:
            cause = ("Reportnet's schema service was briefly unavailable (seen for about "
                     "30 seconds on the sandbox; nothing was written then)")
        else:
            cause = f"the server answered HTTP {status_code}"
        super().__init__(status_code, response_body)
        self.args = (
            f"{operation}: {cause}. The change may be partly applied — read the "
            f"schema again before retrying. Response: {response_body[:300]}",
        )

    def __str__(self) -> str:
        return str(self.args[0])


class SchemaDesignError(ReportnetError):
    """A schema change was refused by the client's own safety checks.

    Nothing was sent to Reportnet. The message says why and, where one exists,
    which argument overrides the check.
    """


class TableHasDataError(SchemaDesignError):
    """The table holds records, so its definition must not change.

    The web app locks such a table ("Delete the data first if you want to
    modify the schema"), but the API accepts the change anyway (verified on
    sandbox design dataset 33796, 2026-11-12). Pass ``force=True`` to override.
    """

    def __init__(self, table: str, records: int) -> None:
        self.table = table
        self.records = records
        super().__init__(
            f"Table {table!r} holds {records} record(s); Reportnet's web app locks its "
            "definition until the data is deleted. Delete the data first, or pass "
            "force=True if you are sure."
        )


class DuplicateNameError(SchemaDesignError):
    """A table or field with this name already exists.

    The API accepts duplicates (two "Sites" tables were created in one sandbox
    dataset on 2026-11-12); the web app does not.
    """


class SchemaReadbackError(SchemaDesignError):
    """A schema change was accepted, but reading the schema back shows otherwise.

    The change may be partly applied. ``expected`` and ``actual`` hold the
    properties that differ.
    """

    def __init__(self, operation: str, expected: dict[str, object],
                 actual: dict[str, object]) -> None:
        self.operation = operation
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"{operation} was accepted but the schema read back differs: "
            f"expected {expected}, found {actual}. Read the schema before retrying."
        )
