"""Real Databricks adapter — connects with databricks-sql-connector.

Databricks auth is structurally different from Snowflake: no account/
warehouse/role model. Instead it needs a workspace hostname, an HTTP path
to a SQL warehouse, and a personal access token. Unity Catalog also adds a
third namespace level (catalog.schema.table) that Snowflake doesn't have.
"""
import os
from datetime import datetime, timezone
import re


def _connect():
    from databricks import sql

    hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME")
    http_path = os.getenv("DATABRICKS_HTTP_PATH")
    token = os.getenv("DATABRICKS_ACCESS_TOKEN")
    if not hostname or not http_path or not token:
        raise RuntimeError(
            "Databricks credentials missing. Set DATABRICKS_SERVER_HOSTNAME, "
            "DATABRICKS_HTTP_PATH, and DATABRICKS_ACCESS_TOKEN in .env."
        )
    return sql.connect(server_hostname=hostname, http_path=http_path, access_token=token)


def _qualify(stmt: str) -> str:
    """Prefixes CREATE TABLE <name> with catalog.schema if configured, since
    Unity Catalog needs the full three-level name to know where to create it."""
    catalog = os.getenv("DATABRICKS_CATALOG")
    schema = os.getenv("DATABRICKS_SCHEMA")
    if not catalog or not schema:
        return stmt
    return re.sub(
        r"(CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)([\w.]+)",
        rf"\1{catalog}.{schema}.\2",
        stmt, count=1, flags=re.I,
    )


def dry_run(ddl_statements: list) -> list:
    """Databricks has no DDL EXPLAIN/dry-run; relies on prior syntax validation."""
    results = []
    for stmt in ddl_statements:
        label = stmt[:80] + ("..." if len(stmt) > 80 else "")
        results.append({"statement": label, "dryRunStatus": "unverified",
                        "detail": "Databricks has no DDL dry-run/EXPLAIN; relying on prior syntax validation"})
    return results


def deploy(ddl_statements: list, run_id: str) -> dict:
    created = []
    conn = _connect()
    try:
        cur = conn.cursor()
        for stmt in ddl_statements:
            qualified = _qualify(stmt)
            cur.execute(qualified)
            m = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([\w.]+)`?', qualified, re.I)
            name = m.group(1) if m else "UNKNOWN_OBJECT"
            created.append(name)
        cur.close()
    except Exception as e:
        conn.close()
        return {"status": "failed", "objectsCreated": created, "error": str(e)}
    conn.close()
    return {"status": "success", "objectsCreated": created}