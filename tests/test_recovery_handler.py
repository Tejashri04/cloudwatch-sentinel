import json
import time

import boto3
import pytest
from moto import mock_aws

from sentinel.recovery_handler import lambda_handler


def create_test_tables(dynamodb):
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


def configure_environment(monkeypatch):
    monkeypatch.setenv(
        "APPLICATION_LOG_GROUP",
        "/cloudwatch-sentinel/application",
    )
    monkeypatch.setenv("INCIDENT_TABLE", "test-incidents")
    monkeypatch.setenv(
        "PROCESSED_EVENTS_TABLE",
        "test-processed-events",
    )
    monkeypatch.setenv(
        "NOTIFICATION_OUTBOX_TABLE",
        "test-notification-outbox",
    )


class FakeLogsClient:
    def __init__(self, events):
        self.events = events

    def filter_log_events(self, **kwargs):
        return {"events": self.events}


def create_heartbeat_event():
    return {
        "timestamp": int(time.time() * 1000),
        "message": json.dumps({
            "service": "OrderService",
            "level": "INFO",
            "event_type": "HEARTBEAT",
            "message": "Application health check successful",
            "error_type": "",
        }),
    }


@mock_aws
def test_recovery_handler_keeps_active_incident(
    monkeypatch,
):
    configure_environment(monkeypatch)

    dynamodb = boto3.client(
        "dynamodb",
        region_name="ap-south-1",
    )
    create_test_tables(dynamodb)

    dynamodb.put_item(
        TableName="test-incidents",
        Item={
            "fingerprint": {"S": "TIMEOUT:timeouterror"},
            "category": {"S": "TIMEOUT"},
            "severity": {"S": "HIGH"},
            "services": {"SS": ["OrderService"]},
            "event_count": {"N": "1"},
            "root_cause_hint": {"S": "Check dependency latency"},
            "status": {"S": "OPEN"},
            "missing_runs": {"N": "0"},
            "first_seen": {"N": "100"},
            "last_seen": {"N": "100"},
        },
    )

    logs = FakeLogsClient([
        {
            "timestamp": int(time.time() * 1000),
            "message": json.dumps({
                "service": "OrderService",
                "level": "ERROR",
                "error_type": "TimeoutError",
                "message": "Order request timed out",
            })
        },
        create_heartbeat_event(),
    ])

    response = lambda_handler(
        {},
        None,
        logs_client=logs,
        dynamodb_client=dynamodb,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["active_incidents"] == 1
    assert result["resolved_incidents"] == []

    incident = dynamodb.get_item(
        TableName="test-incidents",
        Key={"fingerprint": {"S": "TIMEOUT:timeouterror"}},
    )["Item"]

    assert incident["status"]["S"] == "OPEN"
    assert incident["missing_runs"]["N"] == "0"


@mock_aws
def test_recovery_handler_skips_empty_logs(monkeypatch):
    configure_environment(monkeypatch)

    dynamodb = boto3.client(
        "dynamodb",
        region_name="ap-south-1",
    )
    create_test_tables(dynamodb)

    logs = FakeLogsClient([])

    response = lambda_handler(
        {},
        None,
        logs_client=logs,
        dynamodb_client=dynamodb,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["recovery_skipped"] is True
    assert result["logs_fetched"] == 0


def test_recovery_handler_requires_environment_variables(
    monkeypatch,
):
    monkeypatch.delenv("APPLICATION_LOG_GROUP", raising=False)
    monkeypatch.delenv("INCIDENT_TABLE", raising=False)
    monkeypatch.delenv("PROCESSED_EVENTS_TABLE", raising=False)
    monkeypatch.delenv(
        "NOTIFICATION_OUTBOX_TABLE",
        raising=False,
    )

    with pytest.raises(ValueError):
        lambda_handler({}, None)



class FailingLogsClient:
    def filter_log_events(self, **kwargs):
        raise RuntimeError("CloudWatch is unavailable")


@mock_aws
def test_recovery_handler_does_not_modify_state_on_cloudwatch_failure(
    monkeypatch,
):
    configure_environment(monkeypatch)

    dynamodb = boto3.client(
        "dynamodb",
        region_name="ap-south-1",
    )
    create_test_tables(dynamodb)

    dynamodb.put_item(
        TableName="test-incidents",
        Item={
            "fingerprint": {"S": "TIMEOUT:timeouterror"},
            "category": {"S": "TIMEOUT"},
            "severity": {"S": "HIGH"},
            "services": {"SS": ["OrderService"]},
            "event_count": {"N": "1"},
            "root_cause_hint": {"S": "Check dependency latency"},
            "status": {"S": "OPEN"},
            "missing_runs": {"N": "1"},
            "first_seen": {"N": "100"},
            "last_seen": {"N": "100"},
        },
    )

    with pytest.raises(RuntimeError, match="CloudWatch is unavailable"):
        lambda_handler(
            {},
            None,
            logs_client=FailingLogsClient(),
            dynamodb_client=dynamodb,
        )

    incident = dynamodb.get_item(
        TableName="test-incidents",
        Key={"fingerprint": {"S": "TIMEOUT:timeouterror"}},
    )["Item"]

    assert incident["status"]["S"] == "OPEN"
    assert incident["missing_runs"]["N"] == "1"


@mock_aws
def test_recovery_handler_resolves_incident_and_creates_notification(
    monkeypatch,
):
    configure_environment(monkeypatch)

    dynamodb = boto3.client(
        "dynamodb",
        region_name="ap-south-1",
    )
    create_test_tables(dynamodb)

    fingerprint = "TIMEOUT:timeouterror"

    dynamodb.put_item(
        TableName="test-incidents",
        Item={
            "fingerprint": {"S": fingerprint},
            "category": {"S": "TIMEOUT"},
            "severity": {"S": "HIGH"},
            "services": {"SS": ["OrderService"]},
            "event_count": {"N": "1"},
            "root_cause_hint": {"S": "Check dependency latency"},
            "status": {"S": "OPEN"},
            "missing_runs": {"N": "1"},
            "first_seen": {"N": "100"},
            "last_seen": {"N": "100"},
        },
    )

    logs = FakeLogsClient([
        {
            "timestamp": int(time.time() * 1000),
            "message": json.dumps({
                "service": "OrderService",
                "level": "INFO",
                "message": "Application is running normally",
            })
        },
        create_heartbeat_event(),
    ])

    response = lambda_handler(
        {},
        None,
        logs_client=logs,
        dynamodb_client=dynamodb,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["active_incidents"] == 0
    assert fingerprint in result["resolved_incidents"]

    incident = dynamodb.get_item(
        TableName="test-incidents",
        Key={"fingerprint": {"S": fingerprint}},
    )["Item"]

    assert incident["status"]["S"] == "RESOLVED"
    assert incident["missing_runs"]["N"] == "2"

    outbox_items = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    assert len(outbox_items) == 1
    assert outbox_items[0]["status"]["S"] == "PENDING"
    assert (
        outbox_items[0]["notification_type"]["S"]
        == "INCIDENT_RECOVERED"
    )



@mock_aws
def test_recovery_handler_skips_when_heartbeat_is_missing(
    monkeypatch,
):
    configure_environment(monkeypatch)

    dynamodb = boto3.client(
        "dynamodb",
        region_name="ap-south-1",
    )
    create_test_tables(dynamodb)

    fingerprint = "TIMEOUT:timeouterror"

    dynamodb.put_item(
        TableName="test-incidents",
        Item={
            "fingerprint": {"S": fingerprint},
            "category": {"S": "TIMEOUT"},
            "severity": {"S": "HIGH"},
            "services": {"SS": ["OrderService"]},
            "event_count": {"N": "1"},
            "root_cause_hint": {"S": "Check dependency latency"},
            "status": {"S": "OPEN"},
            "missing_runs": {"N": "1"},
            "first_seen": {"N": "100"},
            "last_seen": {"N": "100"},
        },
    )

    logs = FakeLogsClient([
        {
            "timestamp": int(time.time() * 1000),
            "message": json.dumps({
                "service": "OrderService",
                "level": "INFO",
                "message": "Application is running normally",
            }),
        }
    ])

    response = lambda_handler(
        {},
        None,
        logs_client=logs,
        dynamodb_client=dynamodb,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["recovery_skipped"] is True
    assert result["reason"] == "No recent application heartbeat"

    incident = dynamodb.get_item(
        TableName="test-incidents",
        Key={"fingerprint": {"S": fingerprint}},
    )["Item"]

    assert incident["status"]["S"] == "OPEN"
    assert incident["missing_runs"]["N"] == "1"



@mock_aws
def test_recovery_handler_skips_when_heartbeat_is_old(
    monkeypatch,
):
    configure_environment(monkeypatch)

    dynamodb = boto3.client(
        "dynamodb",
        region_name="ap-south-1",
    )
    create_test_tables(dynamodb)

    fingerprint = "TIMEOUT:timeouterror"

    dynamodb.put_item(
        TableName="test-incidents",
        Item={
            "fingerprint": {"S": fingerprint},
            "category": {"S": "TIMEOUT"},
            "severity": {"S": "HIGH"},
            "services": {"SS": ["OrderService"]},
            "event_count": {"N": "1"},
            "root_cause_hint": {"S": "Check dependency latency"},
            "status": {"S": "OPEN"},
            "missing_runs": {"N": "1"},
            "first_seen": {"N": "100"},
            "last_seen": {"N": "100"},
        },
    )

    old_timestamp = int(time.time() * 1000) - 20 * 60 * 1000

    logs = FakeLogsClient([
        {
            "timestamp": old_timestamp,
            "message": json.dumps({
                "service": "OrderService",
                "level": "INFO",
                "event_type": "HEARTBEAT",
                "message": "Application health check successful",
            }),
        }
    ])

    response = lambda_handler(
        {},
        None,
        logs_client=logs,
        dynamodb_client=dynamodb,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["recovery_skipped"] is True
    assert result["reason"] == "No recent application heartbeat"

    incident = dynamodb.get_item(
        TableName="test-incidents",
        Key={"fingerprint": {"S": fingerprint}},
    )["Item"]

    assert incident["status"]["S"] == "OPEN"
    assert incident["missing_runs"]["N"] == "1"
