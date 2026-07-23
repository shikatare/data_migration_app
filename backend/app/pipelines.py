
from pathlib import Path
from app import config

PIPELINES = {
    "mysql_snowflake": {
        "label": "MySQL → Snowflake",
        "sourceLabel": "MySQL",
        "targetLabel": "Snowflake",
        "sampleSchemaDir": config.APP_DIR / "data" / "sample_schemas" / "mysql_snowflake",
        "sqlDialect": "snowflake",
        "sourceModeVar": "MYSQL_MODE",
        "targetModeVar": "SNOWFLAKE_MODE",
    },
    "redshift_databricks": {
        "label": "Redshift → Databricks",
        "sourceLabel": "Redshift",
        "targetLabel": "Databricks",
        "sampleSchemaDir": config.APP_DIR / "data" / "sample_schemas" / "redshift_databricks",
        "sqlDialect": "databricks",
        "sourceModeVar": "REDSHIFT_MODE",
        "targetModeVar": "DATABRICKS_MODE",
    },
}

DEFAULT_PIPELINE = "mysql_snowflake"


def get_pipeline(key: str) -> dict:
    if key not in PIPELINES:
        raise ValueError(f"Unknown pipeline '{key}'. Valid options: {list(PIPELINES.keys())}")
    return PIPELINES[key]


def list_pipelines() -> list:
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "sampleSchemaDir"}}
            for k, v in PIPELINES.items()]