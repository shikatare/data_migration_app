
import os


def put_run_record(record: dict) -> dict:
    import boto3
    from boto3.dynamodb.types import TypeSerializer  # noqa: F401
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION")).Table(
        os.getenv("AWS_DYNAMO_TABLE"))
    table.put_item(Item=record)
    return record


def get_run_history() -> list:
    import boto3
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION")).Table(
        os.getenv("AWS_DYNAMO_TABLE"))
    return table.scan().get("Items", [])