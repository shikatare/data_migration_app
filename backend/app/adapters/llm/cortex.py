


def complete(system_prompt: str, user_prompt: str) -> str:
    raise NotImplementedError(
        "Cortex provider not configured. Set SNOWFLAKE_* credentials and call "
        "SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', <prompt>) via the "
        "snowflake connector, returning the JSON string.")