
import json
from app.adapters import llm
from app.pipelines import get_pipeline

MYSQL_SNOWFLAKE_RULES = """
MySQL -> Snowflake type mapping rules (apply exactly):
- VARCHAR(n) -> VARCHAR(n)
- CHAR(n) -> CHAR(n)
- TEXT / MEDIUMTEXT / LONGTEXT / TINYTEXT -> VARCHAR (Snowflake VARCHAR supports up to 16MB)
- INT / INTEGER -> NUMBER(10,0)
- BIGINT -> NUMBER(19,0)
- SMALLINT -> NUMBER(5,0)
- TINYINT -> NUMBER(3,0) (or BOOLEAN if it's clearly a 0/1 flag column)
- DECIMAL(p,s) / NUMERIC(p,s) -> NUMBER(p,s)
- FLOAT / DOUBLE -> FLOAT
- DATE -> DATE
- DATETIME / TIMESTAMP -> TIMESTAMP_NTZ
- BOOLEAN / BOOL -> BOOLEAN
- BLOB / TINYBLOB / MEDIUMBLOB / LONGBLOB -> BINARY
- JSON -> VARIANT with a warning (semi-structured, needs review)
- ENUM(...) -> VARCHAR with a warning (Snowflake has no ENUM type; the check is dropped)
- SET(...) -> VARCHAR with a warning (no direct Snowflake equivalent)
- YEAR -> NUMBER(4,0) with a note
"""

MYSQL_SNOWFLAKE_FEW_SHOT = """
Example 1:
MySQL: CREATE TABLE ACCOUNTS (ACCOUNT_ID INT NOT NULL AUTO_INCREMENT, OPENED_ON DATE NOT NULL, BALANCE DECIMAL(14,2), CONSTRAINT PK_ACCOUNTS PRIMARY KEY (ACCOUNT_ID));
Snowflake: CREATE TABLE ACCOUNTS (ACCOUNT_ID NUMBER(10,0) NOT NULL, OPENED_ON DATE NOT NULL, BALANCE NUMBER(14,2), CONSTRAINT PK_ACCOUNTS PRIMARY KEY (ACCOUNT_ID));

Example 2:
MySQL: CREATE TABLE DOCS (DOC_ID INT NOT NULL AUTO_INCREMENT, BODY LONGTEXT, TAGS JSON, STATUS ENUM('DRAFT','PUBLISHED'), CONSTRAINT PK_DOCS PRIMARY KEY (DOC_ID));
Snowflake: CREATE TABLE DOCS (DOC_ID NUMBER(10,0) NOT NULL, BODY VARCHAR, TAGS VARIANT, STATUS VARCHAR, CONSTRAINT PK_DOCS PRIMARY KEY (DOC_ID));
-- warning: TAGS converted from JSON to VARIANT; verify downstream parsing logic
-- warning: STATUS converted from ENUM to VARCHAR; the ENUM value check is not enforced in Snowflake
"""

REDSHIFT_DATABRICKS_RULES = """
Redshift -> Databricks (Delta Lake) type mapping rules (apply exactly):
- VARCHAR(n) / CHARACTER VARYING(n) -> STRING (Databricks STRING has no length limit;
  note this as a behavior change, not silently ignore it)
- CHAR(n) -> STRING
- INTEGER / INT4 -> INT
- BIGINT / INT8 -> BIGINT
- SMALLINT / INT2 -> SMALLINT
- DECIMAL(p,s) / NUMERIC(p,s) -> DECIMAL(p,s)
- REAL / FLOAT4 -> FLOAT
- DOUBLE PRECISION / FLOAT8 -> DOUBLE
- BOOLEAN -> BOOLEAN
- DATE -> DATE
- TIMESTAMP -> TIMESTAMP (Databricks TIMESTAMP is timezone-aware; Redshift's is not —
  flag this as a warning, do not silently assume equivalence)
- TIMESTAMPTZ -> TIMESTAMP
- SUPER (semi-structured) -> STRING with a warning (store as JSON text; consider STRUCT/MAP/ARRAY
  if the shape is known and stable)
- GEOMETRY / GEOGRAPHY -> STRING with a warning (no native spatial type in Databricks SQL)
- IDENTITY(seed, step) columns -> use "GENERATED ALWAYS AS IDENTITY" in the Databricks column
  definition instead of Redshift's IDENTITY(seed, step) syntax
- DISTKEY / SORTKEY clauses have NO Databricks equivalent — drop them from the generated DDL
  and add a warning noting Z-ORDER BY or liquid clustering as the closest replacement
- Every CREATE TABLE must include "USING DELTA" (Databricks/Delta Lake requires an explicit
  table format; omitting it is a common and serious error)
"""

REDSHIFT_DATABRICKS_FEW_SHOT = """
Example 1:
Redshift: CREATE TABLE ACCOUNTS (ACCOUNT_ID INTEGER IDENTITY(1,1) NOT NULL, OPENED_ON DATE NOT NULL, BALANCE DECIMAL(14,2)) DISTKEY(ACCOUNT_ID) SORTKEY(ACCOUNT_ID);
Databricks: CREATE TABLE ACCOUNTS (ACCOUNT_ID BIGINT GENERATED ALWAYS AS IDENTITY, OPENED_ON DATE NOT NULL, BALANCE DECIMAL(14,2)) USING DELTA;
-- warning: DISTKEY/SORTKEY on ACCOUNT_ID dropped; no Databricks equivalent, consider Z-ORDER BY (ACCOUNT_ID)

Example 2:
Redshift: CREATE TABLE DOCS (DOC_ID INTEGER IDENTITY(1,1) NOT NULL, BODY VARCHAR(65535), TAGS SUPER) DISTKEY(DOC_ID);
Databricks: CREATE TABLE DOCS (DOC_ID BIGINT GENERATED ALWAYS AS IDENTITY, BODY STRING, TAGS STRING) USING DELTA;
-- warning: TAGS converted from SUPER to STRING; verify downstream parsing logic (or model as STRUCT/MAP if schema is known)
-- warning: DISTKEY on DOC_ID dropped; no Databricks equivalent
"""

_PIPELINE_PROMPTS = {
    "mysql_snowflake": (MYSQL_SNOWFLAKE_RULES, MYSQL_SNOWFLAKE_FEW_SHOT),
    "redshift_databricks": (REDSHIFT_DATABRICKS_RULES, REDSHIFT_DATABRICKS_FEW_SHOT),
}


def _system_prompt(pipeline: str) -> str:
    p = get_pipeline(pipeline)
    rules, few_shot = _PIPELINE_PROMPTS[pipeline]
    return f"""You are the Convert Agent in a {p['sourceLabel']}-to-{p['targetLabel']} migration pipeline.
You translate {p['sourceLabel']} DDL into {p['targetLabel']}-compatible DDL.

{rules}

{few_shot}

Respond with ONLY a JSON object matching this exact shape, no prose, no markdown fences:
{{
  "converted_tables": [
    {{ "name": "TABLE_NAME", "columns": ["COL1", "COL2"], "ddl": "CREATE TABLE ... ;" }}
  ],
  "warnings": [ {{ "table": "TABLE_NAME", "message": "..." }} ],
  "unmapped_types": [ {{ "table": "TABLE_NAME", "column": "COL", "sourceType": "..." }} ]
}}"""


def _build_user_prompt(schema: dict, feedback: str, pipeline: str) -> str:
    p = get_pipeline(pipeline)
    table_ddls = "\n\n".join(t.get("rawDdl", "") for t in schema["tables"])
    fb = (f"\n\nIMPORTANT — a previous attempt failed validation. Fix these specific issues:\n{feedback}\n"
          if feedback else "")
    extra = (' Every CREATE TABLE must end with USING DELTA; drop DISTKEY/SORTKEY clauses but warn about them.'
             if pipeline == "redshift_databricks" else "")
    return (f"Convert the following {p['sourceLabel']} DDL to {p['targetLabel']} DDL. Preserve all tables "
            f"and columns; apply the type-mapping rules exactly; flag anything without a clean mapping "
            f'in "warnings" and "unmapped_types".{extra}{fb}\n\n{table_ddls}')


def run_convert_agent(schema: dict, pipeline: str, emit, feedback: str = None) -> dict:
    emit("convert", "running",
         "Re-converting with validation feedback..." if feedback
         else "Building conversion prompt with type-mapping rules and few-shot examples...")

    raw = llm.complete(_system_prompt(pipeline), _build_user_prompt(schema, feedback, pipeline), schema, pipeline)
    try:
        parsed = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Convert Agent: LLM did not return valid JSON — {e}")

    converted = parsed.get("converted_tables", [])
    warnings = parsed.get("warnings", [])
    unmapped = parsed.get("unmapped_types", [])
    emit("convert", "success",
         f"Converted {len(converted)} table(s). {len(warnings)} warning(s), {len(unmapped)} unmapped type(s).")
    return {"convertedTables": converted, "warnings": warnings, "unmappedTypes": unmapped}