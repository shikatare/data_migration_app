"""Real MySQL adapter — connects with mysql-connector-python and introspects
INFORMATION_SCHEMA to build the same structured schema shape the mock
adapter returns, so the rest of the pipeline (Convert/Validate/scoring)
doesn't need to know whether the source was mock or real.

Credentials come from the secrets adapter (env vars by default, or AWS
Secrets Manager when SECRETS_MODE=aws), read under the "MYSQL" name —
MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD — plus MYSQL_PORT and
MYSQL_DATABASE read directly from the environment.
"""
import os
from app.adapters.secrets import get_credentials


def _connect(database=None):
    import mysql.connector

    creds = get_credentials("MYSQL")
    if not creds.get("host") or not creds.get("user"):
        raise RuntimeError(
            "MySQL credentials missing. Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD "
            "(and MYSQL_PORT/MYSQL_DATABASE) in .env."
        )
    return mysql.connector.connect(
        host=creds["host"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=creds["user"],
        password=creds.get("password", ""),
        database=database or os.getenv("MYSQL_DATABASE"),
    )


def _column_rows(cur, schema_name, table_name):
    cur.execute(
        """SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                  NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, COLUMN_TYPE
           FROM INFORMATION_SCHEMA.COLUMNS
           WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
           ORDER BY ORDINAL_POSITION""",
        (schema_name, table_name),
    )
    return cur.fetchall()


def _build_raw_ddl(cur, table_name):
    cur.execute(f"SHOW CREATE TABLE `{table_name}`")
    row = cur.fetchone()
    return row[1] if row else ""


def extract_schema(schema_name: str) -> dict:
    conn = _connect(database=schema_name)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'", (schema_name,))
        table_names = [r[0] for r in cur.fetchall()]

        tables = []
        for t in table_names:
            cols = _column_rows(cur, schema_name, t)
            columns = []
            for (name, data_type, char_len, num_prec, num_scale, nullable, col_type) in cols:
                columns.append({
                    "name": name,
                    "type": data_type.upper(),
                    "length": char_len,
                    "precision": num_prec,
                    "scale": num_scale,
                    "nullable": nullable == "YES",
                    "mysqlColumnType": col_type,  # e.g. "enum('a','b')" — kept for review notes
                })
            raw_ddl = _build_raw_ddl(cur, t)
            tables.append({"name": t, "columns": columns, "rawDdl": raw_ddl})
        cur.close()
    finally:
        conn.close()
    return {"schemaName": schema_name, "tables": tables}


def list_available_schemas() -> list:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
            "WHERE SCHEMA_NAME NOT IN ('mysql','information_schema','performance_schema','sys')")
        names = [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return names