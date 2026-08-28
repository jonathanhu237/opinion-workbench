"""Build actual historical schemas, never relabel a current schema as old."""

from longtian_api import database as migrations
from longtian_api.database import Database


def create_legacy_schema(database: Database, version: int) -> None:
    with database.connect() as connection:
        for number in range(1, version + 1):
            getattr(migrations, f"_migrate_to_version_{number}")(connection)
