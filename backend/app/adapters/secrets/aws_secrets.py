
import os
import json


def get_credentials(name: str) -> dict:
    import boto3
    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
    secret = client.get_secret_value(SecretId=name)
    return json.loads(secret["SecretString"])