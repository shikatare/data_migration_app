"""Convert Agent — translates MySQL DDL to Snowflake DDL via the LLM, guided
by explicit type-mapping rules and few-shot examples; returns structured JSON."""
import json
from app.adapters import llm

TYPE_MAP_RULES = """
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

FEW_SHOT = """
Example 1:
MySQL: CREATE TABLE ACCOUNTS (ACCOUNT_ID INT NOT NULL AUTO_INCREMENT, OPENED_ON DATE NOT NULL, BALANCE DECIMAL(14,2), CONSTRAINT PK_ACCOUNTS PRIMARY KEY (ACCOUNT_ID));
Snowflake: CREATE TABLE ACCOUNTS (ACCOUNT_ID NUMBER(10,0) NOT NULL, OPENED_ON DATE NOT NULL, BALANCE NUMBER(14,2), CONSTRAINT PK_ACCOUNTS PRIMARY KEY (ACCOUNT_ID));

Example 2:
MySQL: CREATE TABLE DOCS (DOC_ID INT NOT NULL AUTO_INCREMENT, BODY LONGTEXT, TAGS JSON, STATUS ENUM('DRAFT','PUBLISHED'), CONSTRAINT PK_DOCS PRIMARY KEY (DOC_ID));
Snowflake: CREATE TABLE DOCS (DOC_ID NUMBER(10,0) NOT NULL, BODY VARCHAR, TAGS VARIANT, STATUS VARCHAR, CONSTRAINT PK_DOCS PRIMARY KEY (DOC_ID));
-- warning: TAGS converted from JSON to VARIANT; verify downstream parsing logic
-- warning: STATUS converted from ENUM to VARCHAR; the ENUM value check is not enforced in Snowflake
"""

SYSTEM_PROMPT = f"""You are the Convert Agent in a MySQL-to-Snowflake migration pipeline.
You translate MySQL DDL into Snowflake-compatible DDL.

{TYPE_MAP_RULES}

CRITICAL RULES — do not violate these:
- You MUST preserve every PRIMARY KEY and FOREIGN KEY constraint from the original DDL,
  exactly, in the converted DDL. Never drop a constraint.
- Never write a quoted string as a DEFAULT value for a numeric column (e.g. never write
  DEFAULT '1' for a NUMBER column) — use an unquoted literal instead (DEFAULT 1), or omit
  the DEFAULT entirely if unsure.
- Order the converted_tables list so that any table referenced by a FOREIGN KEY appears
  BEFORE the table that references it.

{FEW_SHOT}

Respond with ONLY a JSON object matching this exact shape, no prose, no markdown fences:
{{
  "converted_tables": [
    {{ "name": "TABLE_NAME", "columns": ["COL1", "COL2"], "ddl": "CREATE TABLE ... ;" }}
  ],
  "warnings": [ {{ "table": "TABLE_NAME", "message": "..." }} ],
  "unmapped_types": [ {{ "table": "TABLE_NAME", "column": "COL", "sourceType": "JSON" }} ]
}}"""


def _build_user_prompt(schema: dict, feedback: str) -> str:
    table_ddls = "\n\n".join(t.get("rawDdl", "") for t in schema["tables"])
    fb = (f"\n\nIMPORTANT — a previous attempt failed validation. Fix these specific issues:\n{feedback}\n"
          if feedback else "")
    return (f"Convert the following MySQL DDL to Snowflake DDL. Preserve all tables and columns; "
            f"apply the type-mapping rules exactly; flag anything without a clean mapping in "
            f'"warnings" and "unmapped_types". Note: AUTO_INCREMENT has no Snowflake equivalent '
            f'and should simply be dropped from the column definition (Snowflake uses IDENTITY/'
            f'AUTOINCREMENT if needed, but omit it here unless asked).{fb}\n\n{table_ddls}')


def run_convert_agent(schema: dict, emit, feedback: str = None) -> dict:
    emit("convert", "running",
         "Re-converting with validation feedback..." if feedback
         else "Building conversion prompt with type-mapping rules and few-shot examples...")

    raw = llm.complete(SYSTEM_PROMPT, _build_user_prompt(schema, feedback), schema)
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