"""Add original-file records; never migrate or scan arbitrary legacy files."""


def migrate(connection):
    connection.execute("ALTER TABLE content_materials ADD COLUMN content_json TEXT")
    connection.execute("""CREATE TABLE media_cache_owner (
        id INTEGER PRIMARY KEY CHECK(id=1), device INTEGER NOT NULL,
        inode INTEGER NOT NULL)""")
    connection.execute("""CREATE TABLE media_cache_policy (
        id INTEGER PRIMARY KEY CHECK(id=1),
        retention_days INTEGER NOT NULL CHECK(retention_days BETWEEN 1 AND 3650),
        capacity_mib INTEGER NOT NULL CHECK(capacity_mib BETWEEN 1 AND 20480),
        revision INTEGER NOT NULL CHECK(revision>=0))""")
    connection.execute("INSERT INTO media_cache_policy VALUES (1,30,1024,0)")
    connection.execute("""CREATE TABLE media_cache_entries (
        sha256 TEXT PRIMARY KEY, handle TEXT NOT NULL UNIQUE,
        byte_size INTEGER NOT NULL CHECK(byte_size BETWEEN 1 AND 6291456),
        mime_type TEXT NOT NULL, created_at INTEGER NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending','ready','cleared')),
        device INTEGER, inode INTEGER,
        CHECK(state!='ready' OR (device IS NOT NULL AND inode IS NOT NULL)))""")
    connection.execute("""CREATE TABLE media_cache_bindings (
        content_id INTEGER NOT NULL REFERENCES search_contents(id),
        sha256 TEXT NOT NULL REFERENCES media_cache_entries(sha256),
        PRIMARY KEY(content_id,sha256))""")
