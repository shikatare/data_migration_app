"""Credential resolution — env vars (dev) or AWS Secrets Manager (prod)."""
import os
from app import config


def get_credentials(name: str) -> dict:
    if config.get("SECRETS_MODE", "env") == "aws":
        from .aws_secrets import get_credentials as aws_get
        return aws_get(name)
    return {
        "host": os.getenv(f"{name}_HOST", ""),
        "user": os.getenv(f"{name}_USER", ""),
        "password": os.getenv(f"{name}_PASSWORD", ""),
    }