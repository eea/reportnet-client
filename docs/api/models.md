# Models

Plain frozen dataclasses that parse API responses. They perform no network I/O
— for the asynchronous job machinery see [Jobs](jobs.md).

## Dataflow

::: reportnet.DataflowInfo

::: reportnet.DataflowContents

::: reportnet.Reporter

## Datasets

::: reportnet.ReportingDataset

::: reportnet.ReferenceDataset

::: reportnet.TestDataset

## Dataset schema

::: reportnet.DatasetSchema

::: reportnet.TableSchema

::: reportnet.FieldSchema

::: reportnet.FieldType

## Validation results

::: reportnet.ValidationResult

::: reportnet.ValidationIssue

## Verification and evidence

Returned by [`export_frames()`][reportnet.DataflowClient.export_frames],
[`prepare_submission()`][reportnet.DataflowClient.prepare_submission] and
[`permission_evidence()`][reportnet.DataflowClient.permission_evidence].
They report what was *checked*, not merely what succeeded.

::: reportnet.ExportResult

::: reportnet.ExportVerification

::: reportnet.ReadbackVerification

::: reportnet.SubmissionResult

::: reportnet.OperationEvidence
