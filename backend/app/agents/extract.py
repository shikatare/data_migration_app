
import re
from app.adapters import mysql

UNMAPPED_MYSQL_TYPES = ["ENUM", "SET", "JSON", "YEAR"]


def run_extract_agent(schema_name: str, emit) -> dict:
    emit("extract", "running", "Connecting to MySQL and retrieving credentials...")
    schema = mysql.extract_schema(schema_name)

    flags = []
    for table in schema["tables"]:
        for col in table["columns"]:
            if (col.get("type") or "").upper() in UNMAPPED_MYSQL_TYPES:
                flags.append({
                    "table": table["name"], "column": col["name"], "type": col["type"],
                    "reason": f"{col['type']} has no clean Snowflake equivalent — review required",
                })
        if table.get("rawDdl") and re.search(r"\bPARTITION\s+BY", table["rawDdl"], re.I):
            flags.append({"table": table["name"],
                          "reason": "Table appears to use MySQL partitioning — review required"})

    emit("extract", "success",
         f"Extracted {len(schema['tables'])} table(s) from {schema_name}. "
         f"{len(flags)} construct(s) flagged for review.")
    return {"schema": schema, "flags": flags}