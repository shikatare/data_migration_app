
import re
import sqlglot


def parse_and_check_syntax(ddl_statements: list, dialect: str) -> list:
    results = []
    for stmt in ddl_statements:
        try:
            sqlglot.parse_one(stmt, read=dialect)
            results.append({"statement": stmt, "valid": True})
        except Exception as e:
            results.append({"statement": stmt, "valid": False, "error": str(e).splitlines()[0]})
    return results


def structural_diff(original_schema: dict, converted_tables: list) -> list:
    diffs = []
    by_name = {t["name"].upper(): t for t in converted_tables}
    for table in original_schema["tables"]:
        converted = by_name.get(table["name"].upper())
        if not converted:
            diffs.append({"table": table["name"], "issue": "missing_in_conversion"})
            continue
        original_cols = [c["name"].upper() for c in table["columns"]]
        converted_cols = [c.upper() for c in converted.get("columns", [])]
        missing = [c for c in original_cols if c not in converted_cols]
        if missing:
            diffs.append({"table": table["name"], "issue": "missing_columns", "columns": missing})
    return diffs


def check_business_rules(converted_tables: list, pipeline: str) -> list:
    violations = []
    for table in converted_tables:
        if not re.match(r"^[A-Z][A-Z0-9_]*$", table["name"]):
            violations.append({"table": table["name"], "rule": "naming_convention",
                               "detail": "Table name should be UPPER_SNAKE_CASE"})
        ddl = table.get("ddl", "")

        if pipeline == "mysql_snowflake":
            if re.search(r"\bENUM\s*\(", ddl, re.I):
                violations.append({"table": table["name"], "rule": "disallowed_type",
                                   "detail": "ENUM syntax has no Snowflake equivalent and must not appear in the converted DDL"})

        if pipeline == "redshift_databricks":
            if not re.search(r"\bUSING\s+DELTA\b", ddl, re.I):
                violations.append({"table": table["name"], "rule": "missing_table_format",
                                   "detail": "CREATE TABLE must include USING DELTA for Databricks/Delta Lake"})
            if re.search(r"\bDISTKEY\s*\(|\bSORTKEY\s*\(", ddl, re.I):
                violations.append({"table": table["name"], "rule": "disallowed_clause",
                                   "detail": "DISTKEY/SORTKEY have no Databricks equivalent and must not appear in the converted DDL"})
            if re.search(r"\bSUPER\b", ddl, re.I):
                violations.append({"table": table["name"], "rule": "disallowed_type",
                                   "detail": "SUPER is a Redshift type with no Databricks equivalent and must not appear in the converted DDL"})
    return violations