
import os
import re
import uuid
import contextlib
from datetime import datetime, timezone

import snowflake.connector

# Mirrors the mock adapter's in-memory deploy log so behaviour is identical.
_deployed = []


def _connect(schema: str | None = None):
    return snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=schema or os.getenv("SNOWFLAKE_SCHEMA"),
    )


def _object_name(stmt: str) -> str:
    m = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TRANSIENT\s+)?(?:TABLE|VIEW)\s+"?(\w+)"?',
                  stmt, re.I)
    return m.group(1) if m else "UNKNOWN_OBJECT"


def _short(stmt: str) -> str:
    return stmt[:80] + ("..." if len(stmt) > 80 else "")


def dry_run(ddl_statements: list) -> list:

    sandbox = f"MIGRATION_DRYRUN_{uuid.uuid4().hex[:8]}".upper()
    results = []
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f'CREATE TRANSIENT SCHEMA "{sandbox}"')
        cur.execute(f'USE SCHEMA "{sandbox}"')
        for stmt in ddl_statements:
            try:
                cur.execute(stmt)
                results.append({"statement": _short(stmt), "dryRunStatus": "ok"})
            except snowflake.connector.errors.ProgrammingError as e:
                results.append({
                    "statement": _short(stmt),
                    "dryRunStatus": "failed",
                    "error": str(e).splitlines()[0],
                })
        return results
    finally:
        # Always tear down the sandbox, even if setup/execution raised.
        with contextlib.suppress(Exception):
            conn.cursor().execute(f'DROP SCHEMA IF EXISTS "{sandbox}"')
        conn.close()


def deploy(ddl_statements: list, run_id: str) -> dict:
   
    conn = _connect()
    created = []
    try:
        cur = conn.cursor()
        for stmt in ddl_statements:
            cur.execute(stmt)
            name = _object_name(stmt)
            created.append(name)
            _deployed.append({
                "runId": run_id,
                "objectName": name,
                "deployedAt": datetime.now(timezone.utc).isoformat(),
            })
        return {"status": "success", "objectsCreated": created}
    finally:
        conn.close()