
import os
import json
from app import config


# ---------------- Deterministic mock converter — MySQL -> Snowflake ----------------

def _map_type_mysql_snowflake(col: dict) -> dict:
    t = (col.get("type") or "").upper()
    length = col.get("length")
    precision = col.get("precision")
    scale = col.get("scale")
    if t == "VARCHAR":
        return {"target": f"VARCHAR({length})" if length else "VARCHAR"}
    if t == "CHAR":
        return {"target": f"CHAR({length})" if length else "CHAR"}
    if t in ("TEXT", "MEDIUMTEXT", "LONGTEXT", "TINYTEXT"):
        return {"target": "VARCHAR"}
    if t in ("INT", "INTEGER"):
        return {"target": "NUMBER(10,0)"}
    if t == "BIGINT":
        return {"target": "NUMBER(19,0)"}
    if t == "SMALLINT":
        return {"target": "NUMBER(5,0)"}
    if t == "TINYINT":
        return {"target": "NUMBER(3,0)"}
    if t in ("DECIMAL", "NUMERIC"):
        if precision is not None and scale is not None:
            return {"target": f"NUMBER({precision},{scale})"}
        if length is not None:
            return {"target": f"NUMBER({length},0)"}
        return {"target": "NUMBER"}
    if t in ("FLOAT", "DOUBLE"):
        return {"target": "FLOAT"}
    if t == "DATE":
        return {"target": "DATE"}
    if t in ("DATETIME", "TIMESTAMP"):
        return {"target": "TIMESTAMP_NTZ"}
    if t in ("BOOLEAN", "BOOL"):
        return {"target": "BOOLEAN"}
    if t in ("BLOB", "TINYBLOB", "MEDIUMBLOB", "LONGBLOB"):
        return {"target": "BINARY",
                "warning": f"{col['name']} converted from {t} to BINARY; verify binary handling"}
    if t == "JSON":
        return {"target": "VARIANT",
                "warning": f"{col['name']} converted from JSON to VARIANT; verify downstream parsing logic",
                "unmapped": True}
    if t == "ENUM":
        return {"target": "VARCHAR",
                "warning": f"{col['name']} converted from ENUM to VARCHAR; the ENUM value check is not enforced",
                "unmapped": True}
    if t == "SET":
        return {"target": "VARCHAR",
                "warning": f"{col['name']} converted from SET to VARCHAR; no direct Snowflake equivalent",
                "unmapped": True}
    if t == "YEAR":
        return {"target": "NUMBER(4,0)",
                "warning": f"{col['name']} converted from YEAR to NUMBER(4,0); confirm downstream usage",
                "unmapped": True}
    return {"target": t or "VARCHAR"}


def _build_ddl_mysql_snowflake(table: dict) -> str:
    col_defs = []
    for col in table["columns"]:
        mapped = _map_type_mysql_snowflake(col)["target"]
        null = " NOT NULL" if col.get("nullable") is False else ""
        col_defs.append(f"{col['name']} {mapped}{null}")
    return f"CREATE TABLE {table['name']} ({', '.join(col_defs)});"


# ---------------- Deterministic mock converter — Redshift -> Databricks ----------------

def _map_type_redshift_databricks(col: dict) -> dict:
    t = (col.get("type") or "").upper()
    precision = col.get("precision")
    scale = col.get("scale")
    if t in ("VARCHAR", "CHARACTER VARYING", "CHAR", "CHARACTER"):
        return {"target": "STRING"}
    if t in ("INTEGER", "INT4", "INT"):
        return {"target": "INT"}
    if t in ("BIGINT", "INT8"):
        return {"target": "BIGINT"}
    if t in ("SMALLINT", "INT2"):
        return {"target": "SMALLINT"}
    if t in ("DECIMAL", "NUMERIC"):
        if precision is not None and scale is not None:
            return {"target": f"DECIMAL({precision},{scale})"}
        return {"target": "DECIMAL"}
    if t in ("REAL", "FLOAT4"):
        return {"target": "FLOAT"}
    if t in ("DOUBLE PRECISION", "FLOAT8", "DOUBLE"):
        return {"target": "DOUBLE"}
    if t == "BOOLEAN":
        return {"target": "BOOLEAN"}
    if t == "DATE":
        return {"target": "DATE"}
    if t in ("TIMESTAMP", "TIMESTAMPTZ"):
        return {"target": "TIMESTAMP",
                "warning": f"{col['name']} converted from Redshift {t} to Databricks TIMESTAMP; "
                           f"Databricks TIMESTAMP is timezone-aware, Redshift's is not — verify semantics"}
    if t == "SUPER":
        return {"target": "STRING",
                "warning": f"{col['name']} converted from SUPER to STRING; verify downstream parsing logic "
                           f"(consider STRUCT/MAP/ARRAY if the shape is known)",
                "unmapped": True}
    if t in ("GEOMETRY", "GEOGRAPHY"):
        return {"target": "STRING",
                "warning": f"{col['name']} converted from {t} to STRING; no native spatial type in Databricks SQL",
                "unmapped": True}
    return {"target": t or "STRING"}


def _build_ddl_redshift_databricks(table: dict) -> str:
    col_defs = []
    for col in table["columns"]:
        mapped = _map_type_redshift_databricks(col)["target"]
        null = " NOT NULL" if col.get("nullable") is False else ""
        col_defs.append(f"{col['name']} {mapped}{null}")
    return f"CREATE TABLE {table['name']} ({', '.join(col_defs)}) USING DELTA;"


def _mock_complete(schema: dict, pipeline: str) -> str:
    is_redshift = pipeline == "redshift_databricks"
    map_fn = _map_type_redshift_databricks if is_redshift else _map_type_mysql_snowflake
    build_fn = _build_ddl_redshift_databricks if is_redshift else _build_ddl_mysql_snowflake

    converted, warnings, unmapped = [], [], []
    for table in schema["tables"]:
        for col in table["columns"]:
            m = map_fn(col)
            if m.get("warning"):
                warnings.append({"table": table["name"], "message": m["warning"]})
            if m.get("unmapped"):
                unmapped.append({"table": table["name"], "column": col["name"],
                                 "sourceType": col.get("type")})
            if is_redshift and col.get("distkey"):
                warnings.append({"table": table["name"],
                                 "message": f"DISTKEY on {col['name']} dropped; no Databricks equivalent "
                                            f"(consider Z-ORDER BY or liquid clustering)"})
            if is_redshift and col.get("sortkey"):
                warnings.append({"table": table["name"],
                                 "message": f"SORTKEY on {col['name']} dropped; consider Z-ORDER BY ({col['name']}) instead"})
        converted.append({
            "name": table["name"],
            "columns": [c["name"] for c in table["columns"]],
            "ddl": build_fn(table),
        })
    return json.dumps({"converted_tables": converted, "warnings": warnings,
                       "unmapped_types": unmapped})


# ---------------- Real Groq ----------------

def _groq_complete(system_prompt: str, user_prompt: str) -> str:
    from langchain_groq import ChatGroq
    llm = ChatGroq(api_key=os.getenv("GROQ_API_KEY"),
                   model="llama-3.3-70b-versatile", temperature=0,
                   model_kwargs={"response_format": {"type": "json_object"}})
    resp = llm.invoke([("system", system_prompt), ("human", user_prompt)])
    return resp.content if isinstance(resp.content, str) else json.dumps(resp.content)


# ---------------- Public API ----------------

def complete(system_prompt: str, user_prompt: str, schema: dict, pipeline: str) -> str:
    provider = config.get("LLM_PROVIDER", "groq")
    if provider == "mock":
        return _mock_complete(schema, pipeline)
    if provider == "groq" and not os.getenv("GROQ_API_KEY"):
        print("[llm] LLM_PROVIDER=groq but GROQ_API_KEY not set — falling back to mock.")
        return _mock_complete(schema, pipeline)
    return _groq_complete(system_prompt, user_prompt)