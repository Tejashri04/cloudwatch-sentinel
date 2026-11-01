import base64
import gzip
import json

import boto3
from moto import mock_aws

from sentinel.lambda_handler import lambda_handler


@mock_aws
def test_lambda_handler_detects_incident(monkeypatch):
    monkeypatch.setenv("INCIDENT_TABLE", "test-incidents")
    monkeypatch.setenv("PROCESSED_EVENTS_TABLE", "test-processed-events")
    monkeypatch.setenv(
        "NOTIFICATION_OUTBOX_TABLE",
        "test-notification-outbox",
    )

    dynamodb = boto3.client("dynamodb", region_name="ap-south-1")

    dynamodb.create_table(
        TableName="test-incidents",
        KeySchema=[
            {"AttributeName": "fingerprint", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "fingerprint", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    dynamodb.create_table(
        TableName="test-processed-events",
        KeySchema=[
            {"AttributeName": "event_id", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "event_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    dynamodb.create_table(
        TableName="test-notification-outbox",
        KeySchema=[
            {"AttributeName": "notification_id", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "notification_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    events = [
        {
            "id": "event-001",
            "timestamp": 1793400000000,
            "message": json.dumps({
                "service": "OrderService",
                "level": "ERROR",
                "error": "TimeoutError",
                "message": "Order request timed out",
            }),
        },
        {
            "id": "event-002",
            "timestamp": 1793400001000,
            "message": json.dumps({
                "service": "InventoryService",
                "level": "ERROR",
                "error": "TimeoutError",
                "message": "Inventory request timed out",
            }),
        },
    ]

    payload = {
        "messageType": "DATA_MESSAGE",
        "logEvents": events,
    }

    compressed_data = gzip.compress(
        json.dumps(payload).encode("utf-8")
    )

    event = {
        "awslogs": {
            "data": base64.b64encode(compressed_data).decode("utf-8")
        }
    }

    response = lambda_handler(
        event,
        None,
        dynamodb_client=dynamodb,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["processed_events"] == 2
    assert result["detected_incidents"] >= 1
    assert result["new_incidents"] == 1
    assert result["updated_incidents"] == 1

    incidents = dynamodb.scan(
        TableName="test-incidents"
    )["Items"]

    assert len(incidents) == 1
    assert int(incidents[0]["event_count"]["N"]) == 2

    processed_items = dynamodb.scan(
        TableName="test-processed-events"
    )["Items"]

    assert len(processed_items) == 2

    outbox_items = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    assert len(outbox_items) == 1
    assert outbox_items[0]["status"]["S"] == "PENDING"
    assert outbox_items[0]["notification_type"]["S"] == "NEW_INCIDENT"

    duplicate_response = lambda_handler(
        event,
        None,
        dynamodb_client=dynamodb,
    )

    duplicate_result = json.loads(duplicate_response["body"])

    assert duplicate_response["statusCode"] == 200
    assert duplicate_result["processed_events"] == 0
    assert duplicate_result["duplicate_events"] == 2

    incidents_after_retry = dynamodb.scan(
        TableName="test-incidents"
    )["Items"]

    assert len(incidents_after_retry) == 1
    assert int(incidents_after_retry[0]["event_count"]["N"]) == 2

    outbox_after_retry = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    assert len(outbox_after_retry) == 1