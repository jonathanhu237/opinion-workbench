"""Semantic validation and product errors for monitoring rules."""

import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from longtian_api.database import Database
from longtian_api.repositories.monitoring_rules import (
    MonitoringRuleNameConflictError,
    MonitoringRuleNotFoundError,
    MonitoringRuleRecord,
    MonitoringRuleRepository,
    MonitoringRuleRepositoryUnavailableError,
    PreparedMonitoringRule,
)
from longtian_api.schemas.monitoring_rules import (
    MonitoringRule,
    MonitoringRuleCreate,
    MonitoringRuleErrorCode,
    MonitoringRuleListResponse,
    MonitoringRuleReplace,
)

MAX_RULE_NAME_LENGTH = 80
MAX_TERM_LENGTH = 100
MAX_TERMS_PER_RULE = 100


class MonitoringRuleRepositoryProtocol(Protocol):
    """Storage operations consumed by the service and test fakes."""

    def initialize(self) -> None: ...

    def list(
        self, *, enabled: bool | None = None
    ) -> tuple[MonitoringRuleRecord, ...]: ...

    def create(self, rule: PreparedMonitoringRule) -> MonitoringRuleRecord: ...

    def replace(
        self, rule_id: int, rule: PreparedMonitoringRule
    ) -> MonitoringRuleRecord: ...

    def delete(self, rule_id: int) -> None: ...


class MonitoringRuleError(Exception):
    """Expected product error translated by the HTTP route."""

    def __init__(
        self, *, status_code: int, code: MonitoringRuleErrorCode, message: str
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


class MonitoringRuleService:
    """Own validation, normalization, and the reusable enabled-rule boundary."""

    def __init__(
        self,
        *,
        repository: MonitoringRuleRepositoryProtocol | None = None,
        database_path: Path | None = None,
    ) -> None:
        if repository is not None and database_path is not None:
            raise ValueError("Provide either repository or database_path, not both.")
        self._database: Database | None = None
        if repository is None:
            self._database = Database(database_path)
            repository = MonitoringRuleRepository(self._database)
        self._repository = repository

    @property
    def database(self) -> Database | None:
        """Return the shared product database when this is not a test fake."""
        return self._database

    def initialize(self) -> None:
        """Initialize storage before the application accepts requests."""
        self._repository.initialize()

    def list_rules(self, *, enabled: bool | None = None) -> MonitoringRuleListResponse:
        try:
            records = self._repository.list(enabled=enabled)
        except MonitoringRuleRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return MonitoringRuleListResponse(
            rules=[_to_public_rule(record) for record in records]
        )

    def list_enabled(self) -> tuple[MonitoringRule, ...]:
        """Return enabled rules for a later collection-task service."""
        return tuple(self.list_rules(enabled=True).rules)

    def create_rule(self, payload: MonitoringRuleCreate) -> MonitoringRule:
        prepared = _prepare_rule(
            name=payload.name,
            monitoring_objects=payload.monitoring_objects,
            issue_keywords=payload.issue_keywords,
            enabled=payload.enabled,
        )
        try:
            record = self._repository.create(prepared)
        except MonitoringRuleNameConflictError:
            raise _name_conflict() from None
        except MonitoringRuleRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return _to_public_rule(record)

    def replace_rule(
        self, rule_id: int, payload: MonitoringRuleReplace
    ) -> MonitoringRule:
        prepared = _prepare_rule(
            name=payload.name,
            monitoring_objects=payload.monitoring_objects,
            issue_keywords=payload.issue_keywords,
            enabled=payload.enabled,
        )
        try:
            record = self._repository.replace(rule_id, prepared)
        except MonitoringRuleNotFoundError:
            raise _not_found() from None
        except MonitoringRuleNameConflictError:
            raise _name_conflict() from None
        except MonitoringRuleRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return _to_public_rule(record)

    def delete_rule(self, rule_id: int) -> None:
        try:
            self._repository.delete(rule_id)
        except MonitoringRuleNotFoundError:
            raise _not_found() from None
        except MonitoringRuleRepositoryUnavailableError:
            raise _storage_unavailable() from None


def _prepare_rule(
    *,
    name: str,
    monitoring_objects: list[str],
    issue_keywords: list[str],
    enabled: bool,
) -> PreparedMonitoringRule:
    trimmed_name = name.strip()
    if not trimmed_name:
        raise _invalid_rule("请输入规则名称。")
    if len(trimmed_name) > MAX_RULE_NAME_LENGTH:
        raise _invalid_rule("规则名称不能超过 80 个字符。")
    compose_monitoring_terms(monitoring_objects, issue_keywords)

    return PreparedMonitoringRule(
        name=trimmed_name,
        normalized_name=_normalize_identity(trimmed_name),
        monitoring_objects=tuple(
            (value.strip(), _normalize_identity(value)) for value in monitoring_objects
        ),
        issue_keywords=tuple(
            (value.strip(), _normalize_identity(value)) for value in issue_keywords
        ),
        enabled=enabled,
    )


def compose_monitoring_terms(
    monitoring_objects: Sequence[str], issue_keywords: Sequence[str]
) -> tuple[str, ...]:
    """Validate ordered input groups and compose bounded object-major queries."""
    if not monitoring_objects:
        raise _invalid_rule("请至少输入一个监控对象。")
    if len(monitoring_objects) > MAX_TERMS_PER_RULE:
        raise _invalid_rule("每条监控规则最多包含 100 个监控对象。")
    if len(issue_keywords) > MAX_TERMS_PER_RULE:
        raise _invalid_rule("每条监控规则最多包含 100 个舆情关键词。")
    if len(monitoring_objects) * max(1, len(issue_keywords)) > MAX_TERMS_PER_RULE:
        raise _invalid_rule(
            "每条监控规则最多生成 100 个搜索词，请减少监控对象或舆情关键词。"
        )

    objects = _validated_terms(monitoring_objects, "监控对象")
    issues = _validated_terms(issue_keywords, "舆情关键词")
    terms = (
        tuple(f"{obj} {issue}" for obj in objects for issue in issues)
        if issues
        else objects
    )
    return _validated_terms(terms, "生成的搜索词")


def _validated_terms(values: Sequence[str], label: str) -> tuple[str, ...]:
    terms: list[str] = []
    identities: set[str] = set()
    for value in values:
        term = value.strip()
        if not term:
            raise _invalid_rule(f"{label}不能为空。")
        if len(term) > MAX_TERM_LENGTH:
            raise _invalid_rule(f"{label}不能超过 100 个字符。")
        identity = _normalize_identity(term)
        if identity in identities:
            raise MonitoringRuleError(
                status_code=422,
                code="duplicate_monitoring_rule_term",
                message=f"{label}不能重复，请检查后重试。",
            )
        identities.add(identity)
        terms.append(term)
    return tuple(terms)


def _normalize_identity(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold().strip()


def _to_public_rule(record: MonitoringRuleRecord) -> MonitoringRule:
    try:
        terms = compose_monitoring_terms(
            record.monitoring_objects, record.issue_keywords
        )
    except MonitoringRuleError:
        raise _storage_unavailable() from None
    return MonitoringRule(
        id=record.id,
        name=record.name,
        monitoring_objects=record.monitoring_objects,
        issue_keywords=record.issue_keywords,
        terms=terms,
        enabled=record.enabled,
    )


def _invalid_rule(message: str) -> MonitoringRuleError:
    return MonitoringRuleError(
        status_code=422,
        code="invalid_monitoring_rule",
        message=message,
    )


def _name_conflict() -> MonitoringRuleError:
    return MonitoringRuleError(
        status_code=409,
        code="monitoring_rule_name_conflict",
        message="已存在同名监控规则。",
    )


def _not_found() -> MonitoringRuleError:
    return MonitoringRuleError(
        status_code=404,
        code="monitoring_rule_not_found",
        message="未找到该监控规则。",
    )


def _storage_unavailable() -> MonitoringRuleError:
    return MonitoringRuleError(
        status_code=503,
        code="monitoring_rule_storage_unavailable",
        message="监控规则暂时无法读取或保存，请稍后重试。",
    )
