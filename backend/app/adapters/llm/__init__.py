"""LLM adapter for the Convert agent.

- groq   : real Groq llama-3.3-70b (needs GROQ_API_KEY)
- cortex : Snowflake Cortex COMPLETE (runs inside Snowflake)
- mock   : deterministic offline converter (no key/network)

If groq is selected but no key is present, we fall back to mock so the
pipeline still runs end to end instead of crashing.
"""
import os
import json
from app import config


# ---------------- Deterministic mock converter ----------------

def _map_type(col: dict) -> dict:
    t = (col.get("type") or "").upper()
    length = col.get("length")
    precision = col.get("precision")
    scale = col.get("scale")
    if t == "VARCHAR":
        return {"snowflake": f"VARCHAR({length})" if length else "VARCHAR"}
    if t == "CHAR":
        return {"snowflake": f"CHAR({length})" if length else "CHAR"}
    if t in ("TEXT", "MEDIUMTEXT", "LONGTEXT", "TINYTEXT"):
        return {"snowflake": "VARCHAR"}
    if t in ("INT", "INTEGER"):
        return {"snowflake": "NUMBER(10,0)"}
    if t == "BIGINT":
        return {"snowflake": "NUMBER(19,0)"}
    if t == "SMALLINT":
        return {"snowflake": "NUMBER(5,0)"}
    if t == "TINYINT":
        return {"snowflake": "NUMBER(3,0)"}
    if t in ("DECIMAL", "NUMERIC"):
        if precision is not None and scale is not None:
            return {"snowflake": f"NUMBER({precision},{scale})"}
        if length is not None:
            return {"snowflake": f"NUMBER({length},0)"}
        return {"snowflake": "NUMBER"}
    if t in ("FLOAT", "DOUBLE"):
        return {"snowflake": "FLOAT"}
    if t == "DATE":
        return {"snowflake": "DATE"}
    if t in ("DATETIME", "TIMESTAMP"):
        return {"snowflake": "TIMESTAMP_NTZ"}
    if t in ("BOOLEAN", "BOOL"):
        return {"snowflake": "BOOLEAN"}
    if t in ("BLOB", "TINYBLOB", "MEDIUMBLOB", "LONGBLOB"):
        return {"snowflake": "BINARY",
                "warning": f"{col['name']} converted from {t} to BINARY; verify binary handling"}
    if t == "JSON":
        return {"snowflake": "VARIANT",
                "warning": f"{col['name']} converted from JSON to VARIANT; verify downstream parsing logic",
                "unmapped": True}
    if t == "ENUM":
        return {"snowflake": "VARCHAR",
                "warning": f"{col['name']} converted from ENUM to VARCHAR; the ENUM value check is not enforced in Snowflake",
                "unmapped": True}
    if t == "SET":
        return {"snowflake": "VARCHAR",
                "warning": f"{col['name']} converted from SET to VARCHAR; no direct Snowflake equivalent",
                "unmapped": True}
    if t == "YEAR":
        return {"snowflake": "NUMBER(4,0)",
                "warning": f"{col['name']} converted from YEAR to NUMBER(4,0); confirm downstream usage",
                "unmapped": True}
    return {"snowflake": t or "VARCHAR"}


def _constraint_clauses(raw_ddl: str) -> list:
    if not raw_ddl:
        return []
    inner = raw_ddl[raw_ddl.find("(") + 1: raw_ddl.rfind(")")]
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return [p for p in parts if p.upper().startswith("CONSTRAINT")]


def _build_ddl(table: dict) -> str:
    col_defs = []
    for col in table["columns"]:
        snow = _map_type(col)["snowflake"]
        null = " NOT NULL" if col.get("nullable") is False else ""
        col_defs.append(f"{col['name']} {snow}{null}")
    clauses = col_defs + _constraint_clauses(table.get("rawDdl", ""))
    return f"CREATE TABLE {table['name']} ({', '.join(clauses)});"


def _mock_complete(schema: dict) -> str:
    converted, warnings, unmapped = [], [], []
    for table in schema["tables"]:
        for col in table["columns"]:
            m = _map_type(col)
            if m.get("warning"):
                warnings.append({"table": table["name"], "message": m["warning"]})
            if m.get("unmapped"):
                unmapped.append({"table": table["name"], "column": col["name"],
                                 "sourceType": col.get("type")})
        converted.append({
            "name": table["name"],
            "columns": [c["name"] for c in table["columns"]],
            "ddl": _build_ddl(table),
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

def complete(system_prompt: str, user_prompt: str, schema: dict) -> str:
    provider = config.get("LLM_PROVIDER", "groq")
    if provider == "mock":
        return _mock_complete(schema)
    if provider == "groq" and not os.getenv("GROQ_API_KEY"):
        print("[llm] LLM_PROVIDER=groq but GROQ_API_KEY not set — falling back to mock.")
        return _mock_complete(schema)
    if provider == "cortex":
        from .cortex import complete as cortex_complete
        return cortex_complete(system_prompt, user_prompt)
    return _groq_complete(system_prompt, user_prompt)