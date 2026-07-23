
from app.pipelines import get_pipeline

UNMAPPED_TYPES = {
    "mysql_snowflake": ["ENUM", "SET", "JSON", "YEAR"],
    "redshift_databricks": ["SUPER", "GEOMETRY", "GEOGRAPHY", "HLLSKETCH"],
}


def _source_adapter(pipeline: str):
    if pipeline == "mysql_snowflake":
        from app.adapters import mysql
        return mysql
    from app.adapters import redshift
    return redshift


def run_extract_agent(schema_name: str, pipeline: str, emit) -> dict:
    p = get_pipeline(pipeline)
    adapter = _source_adapter(pipeline)
    emit("extract", "running", f"Connecting to {p['sourceLabel']} and retrieving credentials...")
    schema = adapter.extract_schema(schema_name, p["sampleSchemaDir"])

    unmapped = UNMAPPED_TYPES.get(pipeline, [])
    flags = []
    for table in schema["tables"]:
        for col in table["columns"]:
            if (col.get("type") or "").upper() in unmapped:
                flags.append({
                    "table": table["name"], "column": col["name"], "type": col["type"],
                    "reason": f"{col['type']} has no clean {p['targetLabel']} equivalent — review required",
                })
            if col.get("distkey"):
                flags.append({
                    "table": table["name"], "column": col["name"],
                    "reason": "DISTKEY has no Databricks equivalent (Databricks uses Z-ordering/liquid "
                              "clustering instead) — the physical layout hint will be dropped",
                })
            if col.get("sortkey"):
                flags.append({
                    "table": table["name"], "column": col["name"],
                    "reason": "SORTKEY has no direct Databricks equivalent — consider Z-ORDER BY on "
                              "this column after migration",
                })
        raw_ddl_upper = (table.get("rawDdl", "") or "").upper()
        if pipeline == "mysql_snowflake" and "PARTITION BY" in raw_ddl_upper:
            flags.append({"table": table["name"],
                          "reason": "Table appears to use MySQL partitioning — review required"})
        if pipeline == "redshift_databricks" and "IDENTITY" in raw_ddl_upper:
            flags.append({"table": table["name"],
                          "reason": "IDENTITY column found — Databricks uses GENERATED ALWAYS AS IDENTITY, "
                                    "syntax differs from Redshift's IDENTITY(seed, step)"})

    emit("extract", "success",
         f"Extracted {len(schema['tables'])} table(s) from {schema_name}. "
         f"{len(flags)} construct(s) flagged for review.")
    return {"schema": schema, "flags": flags}