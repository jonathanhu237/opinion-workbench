"""Test-only setup for databases that require an explicit collection rule.

The application intentionally creates fresh databases without monitoring rules.
Most legacy regression fixtures exercise collection/report code and therefore
need to create their own neutral rule before using foreign-key references.
"""

from typing import Any

from opinion_workbench_api.database import Database
from opinion_workbench_api.schemas.monitoring_rules import MonitoringRuleCreate
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService

TEST_RULE_NAME = "测试采集规则"
TEST_RULE_OBJECTS = ("测试对象",)


def create_test_rule(
    database: Database,
    *,
    name: str = TEST_RULE_NAME,
    monitoring_objects: tuple[str, ...] = TEST_RULE_OBJECTS,
) -> None:
    MonitoringRuleService(database_path=database.path).create_rule(
        MonitoringRuleCreate(
            name=name,
            monitoring_objects=list(monitoring_objects),
            issue_keywords=[],
            enabled=True,
        )
    )


def ensure_test_rule(
    database: Database,
    *,
    name: str = TEST_RULE_NAME,
    monitoring_objects: tuple[str, ...] = TEST_RULE_OBJECTS,
) -> None:
    service = MonitoringRuleService(database_path=database.path)
    if service.list_rules().rules:
        return
    create_test_rule(
        database,
        name=name,
        monitoring_objects=monitoring_objects,
    )


def initialize_database(database: Database) -> Database:
    database.initialize()
    ensure_test_rule(database)
    return database


def initialize_repository(repository: Any) -> Any:
    repository.initialize()
    database = getattr(repository, "_database", None)
    if isinstance(database, Database):
        ensure_test_rule(database)
    return repository


def initialize_monitoring_rules(
    service: MonitoringRuleService,
) -> MonitoringRuleService:
    service.initialize()
    if service.database is not None:
        ensure_test_rule(service.database)
    return service
