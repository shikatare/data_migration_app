
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
SAMPLE_SCHEMAS_DIR = APP_DIR / "data" / "sample_schemas"
RUNS_FILE = APP_DIR / "data" / "runs" / "runs.json"


def get(name: str, default: str) -> str:
    return os.getenv(name, default)


def config_summary() -> dict:
    return {
        "mysqlMode": get("MYSQL_MODE", "mock"),
        "snowflakeMode": get("SNOWFLAKE_MODE", "mock"),
        "llmProvider": get("LLM_PROVIDER", "groq"),
        "secretsMode": get("SECRETS_MODE", "env"),
        "storageMode": get("STORAGE_MODE", "local"),
        "notifyMode": get("NOTIFY_MODE", "console"),
    }