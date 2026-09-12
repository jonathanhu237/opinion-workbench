"""Retire the original-media cache while preserving content evidence."""


def migrate(connection):
    # The cache tables contain only local retention state and file ownership.
    # Saved text and historical input JSON live in content_materials and are
    # deliberately retained.
    for table in (
        "media_cache_bindings",
        "media_cache_entries",
        "media_cache_policy",
        "media_cache_owner",
    ):
        connection.execute(f"DROP TABLE IF EXISTS {table}")
