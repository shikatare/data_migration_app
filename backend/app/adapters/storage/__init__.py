"""Run-history storage — local JSON (mock DynamoDB) or real AWS DynamoDB."""
import json
from app import config


def _read_local() -> list:
    try:
        return json.loads(config.RUNS_FILE.read_text())
    except Exception:
        return []


def _write_local(runs: list) -> None:
    config.RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.RUNS_FILE.write_text(json.dumps(runs, indent=2))


def put_run_record(record: dict) -> dict:
    if config.get("STORAGE_MODE", "local") == "aws":
        from .aws_dynamo import put_run_record as aws_put
        return aws_put(record)
    runs = _read_local()
    runs.insert(0, record)
    _write_local(runs[:200])
    return record


def get_run_history() -> list:
    if config.get("STORAGE_MODE", "local") == "aws":
        from .aws_dynamo import get_run_history as aws_get
        return aws_get()
    return _read_local()


def get_run(run_id: str):
    return next((r for r in get_run_history() if r.get("runId") == run_id), None)