"""Real Snowflake adapter — executes DDL via snowflake-connector-python.

Credentials come from SNOWFLAKE_* env vars (see .env.example). Because a
Snowflake connection needs account/warehouse/database/schema — which the
generic `secrets` adapter (host/user/password) can't express — this module
reads its own SNOWFLAKE_* vars directly.

Return shapes MUST match the mock adapter in ``snowflake/__init__.py``:
  dry_run  -> [ {"statement": str, "dryRunStatus": "ok"|"failed", ...} ]
  deploy   -> {"status": "success", "objectsCreated": [str, ...]}
"""
import os
import re
import uuid
import contextlib
from datetime import datetime, timezone

import snowflake.connector

# Mirrors the mock adapter's in-memory deploy log so behaviour is identical.
_deployed = []


def _connect(schema: str | None = None):
    """Open a Snowflake connection. `schema` overrides the default target
    (used to point at a throwaway sandbox for dry-runs)."""
    return snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=schema or os.getenv("SNOWFLAKE_SCHEMA"),
    )


def _object_name(stmt: str) -> str:
    """Best-effort object name for the deploy log (matches the mock's regex,
    extended to VIEWs)."""
    m = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TRANSIENT\s+)?(?:TABLE|VIEW)\s+"?(\w+)"?',
                  stmt, re.I)
    return m.group(1) if m else "UNKNOWN_OBJECT"


def _short(stmt: str) -> str:
    return stmt[:80] + ("..." if len(stmt) > 80 else "")


def dry_run(ddl_statements: list) -> list:
    """Validate each statement by executing it inside a transient sandbox
    schema, then dropping the schema. Snowflake has no parse-only mode and DDL
    auto-commits (no rollback), so a throwaway schema is the only way to test
    real execution without touching the target.
    """
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
    """Execute DDL against the configured target schema. Statements are assumed
    already ordered (tables before views/FKs) by the upstream Convert agent.
    """
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