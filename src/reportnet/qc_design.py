"""Edit SQL QC rules of a design dataset safely: guards and read-back.

:class:`QcDesigner` composes public :class:`~reportnet.ReportnetClient`
methods and holds no endpoint knowledge. What it adds (verified on sandbox
dataflow 11468, 2026-11-13; see ``notes/api-notes.md``, "QC rules"):

* **Login token only**, and **design datasets only**; refused before any request.
* **SQL rules only.** Automatic rules and expression or relation rules are
  refused with :class:`~reportnet.QcRuleNotEditableError`.
* **Short codes are unique** (case-insensitive). Rules are addressed by short
  code, because the API returns no id when it creates one.
* **Whole-body updates.** Enable and disable are updates with ``enabled`` changed.
* **Read back after every write.** Each method returns the rule as Reportnet
  lists it afterwards, and raises :class:`~reportnet.SchemaReadbackError` if it
  differs from what was asked.

**Reportnet does not check rule SQL through the API.** Rules with a syntax error
or an unknown table were accepted, and "validate all" marked them
``verified: true`` with no error. The only checks here are client-side: the
SQL starts with ``SELECT`` or ``WITH``, and the severity is known. Test the SQL
on data before you rely on a rule.

Example::

    qc = flow.qc(48100)
    qc.add_sql_rule("SQL01", name="Site code exists",
                    sql='SELECT * FROM dataset_48100."sites" WHERE sitecode IS NULL',
                    on="Sites", message="Missing site code", severity="ERROR")
    qc.update_rule("SQL01", message="Every site needs a code")
    qc.disable("SQL01")
    qc.delete_rule("SQL01")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union

from ._log import get_logger
from .exceptions import (
    DuplicateNameError,
    QcRuleNotEditableError,
    QcSqlError,
    SchemaDesignError,
    SchemaDesignNotPermittedError,
    SchemaReadbackError,
)
from .models import FieldSchema, RuleDefinition, RuleSet, Severity, TableSchema
from .public_schema import _SQL_START

if TYPE_CHECKING:
    from .dataflow import DataflowClient

logger = get_logger(__name__)

RuleRef = Union[RuleDefinition, str]
"""A rule, or its short code."""
Target = Union[TableSchema, FieldSchema, str, tuple[str, str]]
"""What a rule checks: a table (object or name), a field, or ``(table, field)`` names."""


def _severity(value: Severity | str) -> str:
    try:
        return Severity(str(getattr(value, "value", value)).upper()).value
    except ValueError:
        raise SchemaDesignError(
            f"Unknown severity {value!r}; use one of {[s.value for s in Severity]}."
        ) from None


def _check_sql(sql: str) -> str:
    if not isinstance(sql, str) or not _SQL_START.match(sql):
        raise QcSqlError("Rule SQL must start with SELECT or WITH. Reportnet does not check "
                         "it, so this client does what little it can.")
    return sql


class QcDesigner:
    """Change one design dataset's SQL QC rules. Obtain via :meth:`DataflowClient.qc`."""

    def __init__(self, flow: "DataflowClient", dataset_id: int) -> None:
        self._flow = flow
        self._client = flow._client
        self.dataset_id = dataset_id
        self.dataflow_id = flow._dataflow_id
        if self._client.auth_kind != "bearer":
            raise SchemaDesignNotPermittedError("QC rule editing")
        design = {d.id: d for d in flow.get_dataflow_contents().design_datasets}
        if dataset_id not in design:
            raise SchemaDesignError(
                f"Dataset {dataset_id} is not a design dataset of dataflow "
                f"{self.dataflow_id}; QC rules are edited on design datasets only. "
                f"Design datasets: {sorted((d.id, d.name) for d in design.values())}"
            )
        self.schema_id = design[dataset_id].schema_id

    # ── reading ───────────────────────────────────────────────────────────────

    def rule_set(self) -> RuleSet:
        """All rules of this dataset's schema, as Reportnet lists them now."""
        return self._client.get_rules(schema_id=self.schema_id, dataflow_id=self.dataflow_id)

    def rules(self, *, sql_only: bool = False) -> list[RuleDefinition]:
        """The rules, automatic ones included unless *sql_only*."""
        return [r for r in self.rule_set().rules if r.is_sql or not sql_only]

    def rule(self, ref: RuleRef) -> RuleDefinition:
        """One rule by short code (case-insensitive) or object, freshly read."""
        code = ref.short_code if isinstance(ref, RuleDefinition) else ref
        found = self.rule_set().by_short_code(code)
        if found is None:
            raise SchemaDesignError(f"No rule with short code {code!r} in dataset "
                                    f"{self.dataset_id}.")
        return found

    # ── writing ───────────────────────────────────────────────────────────────

    def add_sql_rule(
        self, short_code: str, *, name: str, sql: str, on: Target, message: str,
        severity: Severity | str = Severity.ERROR, description: str = "",
        enabled: bool = True, record: bool = False,
    ) -> RuleDefinition:
        """Add an SQL rule; returns it as read back.

        *on* decides the rule type: a table (or its name) gives a TABLE rule, or
        a RECORD rule with ``record=True``; a field, or ``(table, field)``
        names, gives a FIELD rule.
        """
        _check_sql(sql)
        level = _severity(severity)
        if not short_code.strip():
            raise SchemaDesignError("A rule needs a short code.")
        if self.rule_set().by_short_code(short_code) is not None:
            raise DuplicateNameError(f"Dataset {self.dataset_id} already has a rule with "
                                     f"short code {short_code!r}.")
        rule_type, reference_id = self._target(on, record=record)
        body: dict[str, Any] = {
            "automatic": False, "enabled": enabled, "type": rule_type,
            "referenceId": reference_id, "ruleName": name, "shortCode": short_code,
            "description": description, "expressionText": None, "sqlSentence": sql,
            "thenCondition": [message, level], "whenCondition": None,
        }
        if rule_type == "TABLE":
            body["integrityVO"] = None
        self._client.create_rule(dataset_id=self.dataset_id, body=body)
        logger.info("added QC rule %r to dataset %s", short_code, self.dataset_id)
        return self._readback("add_sql_rule", short_code, body)

    def update_rule(
        self, ref: RuleRef, *, name: str | None = None, sql: str | None = None,
        message: str | None = None, severity: Severity | str | None = None,
        description: str | None = None,
    ) -> RuleDefinition:
        """Change an SQL rule; sends the whole rule (read-modify-write)."""
        current = self._editable(ref)
        changes: dict[str, Any] = {}
        if name is not None:
            changes["ruleName"] = name
        if description is not None:
            changes["description"] = description
        if sql is not None:
            changes["sqlSentence"] = _check_sql(sql)
        if message is not None or severity is not None:
            changes["thenCondition"] = [
                current.message if message is None else message,
                current.severity if severity is None else _severity(severity),
            ]
        return self._update("update_rule", current, changes)

    def enable(self, ref: RuleRef) -> RuleDefinition:
        """Switch an SQL rule on."""
        return self._update("enable", self._editable(ref), {"enabled": True})

    def disable(self, ref: RuleRef) -> RuleDefinition:
        """Switch an SQL rule off without deleting it."""
        return self._update("disable", self._editable(ref), {"enabled": False})

    def delete_rule(self, ref: RuleRef) -> None:
        """Delete an SQL rule; checks that it is gone afterwards."""
        current = self._editable(ref)
        self._client.delete_rule(dataset_id=self.dataset_id, rule_id=current.id)
        logger.info("deleted QC rule %r from dataset %s", current.short_code, self.dataset_id)
        if self.rule_set().by_short_code(current.short_code) is not None:
            raise SchemaReadbackError("delete_rule", {"present": False}, {"present": True})

    # ── SQL helpers ───────────────────────────────────────────────────────────

    def test_sql(self, sql: str, *, provider_code: str | None = None) -> Any:
        """Test-run *sql* on this dataset and return Reportnet's answer.

        **Not verified.** On the sandbox it failed on a dataset whose columns
        include a reserved word (``Group``): Reportnet's own wrapper leaves
        column names unquoted (2026-11-13).
        """
        return self._client.run_sql_rule(dataset_id=self.dataset_id, sql=_check_sql(sql),
                                         provider_code=provider_code)

    def validate_all(self) -> None:
        """Ask Reportnet to re-check every SQL rule of this dataset.

        It runs in the background, and on the sandbox it marked invalid SQL as
        ``verified: true``. Do not read ``verified`` as "the SQL is valid".
        """
        self._client.validate_sql_rules(dataset_id=self.dataset_id, schema_id=self.schema_id)

    # ── internals ─────────────────────────────────────────────────────────────

    def _editable(self, ref: RuleRef) -> RuleDefinition:
        rule = self.rule(ref)
        if rule.automatic or not rule.is_sql:
            kind = "automatic" if rule.automatic else "not an SQL rule"
            raise QcRuleNotEditableError(
                f"Rule {rule.short_code!r} is {kind}; this library edits SQL rules only. "
                "Change it in the web app.")
        return rule

    def _update(self, operation: str, current: RuleDefinition,
                changes: dict[str, Any]) -> RuleDefinition:
        body = current.to_body(**changes)
        self._client.update_rule(dataset_id=self.dataset_id, body=body)
        logger.info("%s QC rule %r in dataset %s", operation, current.short_code,
                    self.dataset_id)
        return self._readback(operation, current.short_code, body)

    def _readback(self, operation: str, short_code: str,
                  body: dict[str, Any]) -> RuleDefinition:
        after = self.rule_set().by_short_code(short_code)
        if after is None:
            raise SchemaReadbackError(operation, {"short_code": short_code},
                                      {"short_code": None})
        wanted = {"name": body["ruleName"], "sql": body["sqlSentence"] or None,
                  "message": body["thenCondition"][0], "severity": body["thenCondition"][1],
                  "enabled": body["enabled"], "type": body["type"],
                  "reference_id": body["referenceId"], "description": body["description"] or ""}
        expected = {k: v for k, v in wanted.items() if getattr(after, k) != v}
        if expected:
            raise SchemaReadbackError(operation, expected,
                                      {k: getattr(after, k) for k in expected})
        return after

    def _target(self, on: Target, *, record: bool) -> tuple[str, str]:
        if isinstance(on, FieldSchema):
            return "FIELD", on.id
        schema = self._client.get_schema(dataset_id=self.dataset_id)
        if isinstance(on, tuple):
            table_name, field_name = on
            table = self._table(schema.tables, table_name)
            match = [f for f in table.fields if f.name.casefold() == field_name.casefold()]
            if not match:
                raise SchemaDesignError(f"Table {table.name!r} has no field {field_name!r}.")
            return "FIELD", match[0].id
        table = on if isinstance(on, TableSchema) else self._table(schema.tables, on)
        if record:
            return "RECORD", table.record_id
        return "TABLE", table.id

    @staticmethod
    def _table(tables: tuple[TableSchema, ...], name: str) -> TableSchema:
        match = [t for t in tables if t.name.casefold() == name.casefold() or t.id == name]
        if not match:
            raise SchemaDesignError(
                f"No table {name!r}; tables: {[t.name for t in tables]}")
        return match[0]
