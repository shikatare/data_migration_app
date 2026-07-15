"""Snowflake adapter factory — mock (simulated) or real (snowflake-connector)."""
import re
from datetime import datetime, timezone
from app import config

_deployed = []


def dry_run(ddl_statements: list) -> list:
    if config.get("SNOWFLAKE_MODE", "mock") == "real":
        from .real_snowflake import dry_run as real_dry
        return real_dry(ddl_statements)
    return [
        {"statement": s[:80] + ("..." if len(s) > 80 else ""), "dryRunStatus": "ok"}
        for s in ddl_statements
    ]


def deploy(ddl_statements: list, run_id: str) -> dict:
    if config.get("SNOWFLAKE_MODE", "mock") == "real":
        from .real_snowflake import deploy as real_deploy
        return real_deploy(ddl_statements, run_id)
    created = []
    for stmt in ddl_statements:
        m = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+"?(\w+)"?', stmt, re.I)
        name = m.group(1) if m else "UNKNOWN_OBJECT"
        _deployed.append({"runId": run_id, "objectName": name,
                          "deployedAt": datetime.now(timezone.utc).isoformat()})
        created.append(name)
    return {"status": "success", "objectsCreated": created}