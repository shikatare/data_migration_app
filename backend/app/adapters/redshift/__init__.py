
import json
import os


def _mock_extract_schema(schema_name: str, sample_dir) -> dict:
    file = sample_dir / f"{schema_name}.json"
    return json.loads(file.read_text())


def _mock_list_schemas(sample_dir) -> list:
    return sorted(p.stem for p in sample_dir.glob("*.json"))


def extract_schema(schema_name: str, sample_dir) -> dict:
    mode = os.getenv("REDSHIFT_MODE", "mock")
    if mode == "real":
        from .real_redshift import extract_schema as real_extract
        return real_extract(schema_name)
    return _mock_extract_schema(schema_name, sample_dir)


def list_available_schemas(sample_dir) -> list:
    mode = os.getenv("REDSHIFT_MODE", "mock")
    if mode == "real":
        from .real_redshift import list_available_schemas as real_list
        return real_list()
    return _mock_list_schemas(sample_dir)