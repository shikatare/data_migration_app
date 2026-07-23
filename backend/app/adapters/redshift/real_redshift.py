
import os
from app.adapters.secrets import get_credentials


def _connect(database=None):
    import redshift_connector

    creds = get_credentials("REDSHIFT")
    if not creds.get("host") or not creds.get("user"):
        raise RuntimeError(
            "Redshift credentials missing. Set REDSHIFT_HOST, REDSHIFT_USER, "
            "REDSHIFT_PASSWORD (and REDSHIFT_PORT/REDSHIFT_DATABASE) in .env."
        )
    return redshift_connector.connect(
        host=creds["host"],
        port=int(os.getenv("REDSHIFT_PORT", "5439")),
        user=creds["user"],
        password=creds.get("password", ""),
        database=database or os.getenv("REDSHIFT_DATABASE"),
    )


def _column_rows(cur, schema_name, table_name):
    cur.execute(
        """SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                  NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
           FROM INFORMATION_SCHEMA.COLUMNS
           WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
           ORDER BY ORDINAL_POSITION""",
        (schema_name, table_name),
    )
    return cur.fetchall()


def _dist_sort_keys(cur, schema_name, table_name):
    """Redshift-specific: which column (if any) is the DISTKEY / SORTKEY.
    Neither has a direct Databricks equivalent — flagged by Extract."""
    try:
        cur.execute(
            """SELECT "column", distkey, sortkey
               FROM pg_table_def
               WHERE schemaname = %s AND tablename = %s""",
            (schema_name, table_name),
        )
        rows = cur.fetchall()
        return {r[0]: {"distkey": bool(r[1]), "sortkey": int(r[2]) > 0} for r in rows}
    except Exception:
        return {}


def _build_raw_ddl(table_name, columns, key_info):
    """Redshift has no single SHOW CREATE TABLE; reconstruct DDL from the
    introspected columns, including DISTKEY/SORTKEY annotations."""
    col_lines = []
    for name, dtype, char_len, prec, scale, nullable in columns:
        t = dtype.upper()
        if char_len and t in ("CHARACTER VARYING", "VARCHAR", "CHARACTER", "CHAR"):
            t = f"{t}({char_len})"
        elif prec and t in ("NUMERIC", "DECIMAL"):
            t = f"{t}({prec},{scale or 0})"
        null_clause = "" if nullable == "YES" else " NOT NULL"
        col_lines.append(f"{name} {t}{null_clause}")
    ddl = f"CREATE TABLE {table_name} ({', '.join(col_lines)})"
    dist_cols = [c for c, k in key_info.items() if k.get("distkey")]
    sort_cols = [c for c, k in key_info.items() if k.get("sortkey")]
    if dist_cols:
        ddl += f" DISTKEY({dist_cols[0]})"
    if sort_cols:
        ddl += f" SORTKEY({', '.join(sort_cols)})"
    return ddl + ";"


def extract_schema(schema_name: str) -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'", (schema_name,))
        table_names = [r[0] for r in cur.fetchall()]

        tables = []
        for t in table_names:
            cols = _column_rows(cur, schema_name, t)
            key_info = _dist_sort_keys(cur, schema_name, t)
            columns = []
            for (name, dtype, char_len, prec, scale, nullable) in cols:
                k = key_info.get(name, {})
                columns.append({
                    "name": name,
                    "type": dtype.upper(),
                    "length": char_len,
                    "precision": prec,
                    "scale": scale,
                    "nullable": nullable == "YES",
                    "distkey": k.get("distkey", False),
                    "sortkey": k.get("sortkey", False),
                })
            raw_ddl = _build_raw_ddl(t, cols, key_info)
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
            "WHERE SCHEMA_NAME NOT IN ('information_schema', 'pg_catalog', 'pg_internal')")
        names = [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return names