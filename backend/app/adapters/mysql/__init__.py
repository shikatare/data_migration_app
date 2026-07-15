"""MySQL adapter factory — mock (sample schemas) or real (mysql-connector-python)."""
import json
from app import config


def _mock_extract_schema(schema_name: str) -> dict:
    file = config.SAMPLE_SCHEMAS_DIR / f"{schema_name}.json"
    return json.loads(file.read_text())


def _mock_list_schemas() -> list:
    return sorted(p.stem for p in config.SAMPLE_SCHEMAS_DIR.glob("*.json"))


def extract_schema(schema_name: str) -> dict:
    mode = config.get("MYSQL_MODE", "mock")
    if mode == "real":
        from .real_mysql import extract_schema as real_extract
        return real_extract(schema_name)
    return _mock_extract_schema(schema_name)


def list_available_schemas() -> list:
    mode = config.get("MYSQL_MODE", "mock")
    if mode == "real":
        from .real_mysql import list_available_schemas as real_list
        return real_list()
    return _mock_list_schemas()