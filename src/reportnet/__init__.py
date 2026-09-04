from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from ._util import cast_frame, table_to_frame, to_geodataframe
from .client import PRODUCTION_URL, SANDBOX_URL, ReportnetClient
from .dataflow import DataflowClient
from .exceptions import (
    APIError,
    AuthError,
    CodelistResolutionError,
    DatasetLockedError,
    DiscoveryNotPermittedError,
    JobFailedError,
    JobTimeoutError,
    RateLimitError,
    ReportnetError,
)
from .interactive import connect_interactive
from .jobs import JobHandle, JobStatus
from .keychain import delete_key, get_key, save_key
from .models import (
    Capabilities,
    DataCollection,
    DataflowContents,
    DataflowInfo,
    DatasetSchema,
    EuDataset,
    FieldSchema,
    FieldType,
    ReferenceDataset,
    Reporter,
    ReportingDataset,
    TableSchema,
    TestDataset,
    ValidationIssue,
    ValidationResult,
)
from .providers import PROVIDERS, DataProvider, by_country, by_group, by_id
from .viz import dataflow_to_mermaid

try:
    __version__ = _version("reportnet-client")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0.dev0"

__all__ = [
    "__version__",
    "PRODUCTION_URL",
    "SANDBOX_URL",
    "ReportnetClient",
    "DataflowClient",
    "connect_interactive",
    "dataflow_to_mermaid",
    "JobHandle",
    "JobStatus",
    "DataflowContents",
    "Capabilities",
    "DataflowInfo",
    "Reporter",
    "ReportingDataset",
    "ReferenceDataset",
    "TestDataset",
    "DataCollection",
    "EuDataset",
    "DatasetSchema",
    "TableSchema",
    "FieldSchema",
    "FieldType",
    "cast_frame",
    "table_to_frame",
    "to_geodataframe",
    "ReportnetError",
    "APIError",
    "AuthError",
    "DatasetLockedError",
    "CodelistResolutionError",
    "DiscoveryNotPermittedError",
    "RateLimitError",
    "JobFailedError",
    "JobTimeoutError",
    "ValidationIssue",
    "ValidationResult",
    "DataProvider",
    "PROVIDERS",
    "by_id",
    "by_country",
    "by_group",
    "get_key",
    "save_key",
    "delete_key",
]
