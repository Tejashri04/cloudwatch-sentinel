from uuid import UUID

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

import sentinel.dynamodb_store as dynamodb_store
from sentinel.dynamodb_store import DynamoDBIncidentStore


def create_test_store():
    dynamodb = boto3.client("dynamodb", region_name="ap-south-1")

    tables = [
        ("test-incidents", "fingerprint"),
        ("test-processed-events", "event_id"),
        ("test-notification-outbox", "notification_id"),
    ]

    for table_name, key_name in tables:
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": key_name, "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": key_name, "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )

    store = DynamoDBIncidentStore(
        dynamodb_client=dynamodb,
        incident_table="test-incidents",
        processed_events_table="test-processed-events",
        notification_outbox_table="test-notification-outbox",
    )

    return dynamodb, store


def create_test_incident():
    return {
        "fingerprint": "TIMEOUT:timeouterror",
        "category": "TIMEOUT",
        "severity": "HIGH",
        "services": ["OrderService"],
        "root_cause_hint": "Check dependency latency.",
    }


@mock_aws
def test_process_new_incident_and_duplicate_events():
    dynamodb = boto3.client("dynamodb", region_name="ap-south-1")

    tables = [
        ("test-incidents", "fingerprint"),
        ("test-processed-events", "event_id"),
        ("test-notification-outbox", "notification_id"),
    ]

    for table_name, key_name in tables:
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": key_name, "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": key_name, "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )

    store = DynamoDBIncidentStore(
        dynamodb_client=dynamodb,
        incident_table="test-incidents",
        processed_events_table="test-processed-events",
        notification_outbox_table="test-notification-outbox",
    )

    incident = {
        "fingerprint": "TIMEOUT:timeouterror",
        "category": "TIMEOUT",
        "severity": "HIGH",
        "services": ["OrderService"],
        "root_cause_hint": "Check dependency latency.",
    }

    first_result = store.process_event(
        event_id="event-001",
        incident=incident,
        now=1793400000,
    )

    assert first_result == "NEW"

    duplicate_result = store.process_event(
        event_id="event-001",
        incident=incident,
        now=1793400001,
    )

    assert duplicate_result == "DUPLICATE"

    second_incident = {
        **incident,
        "services": ["InventoryService"],
    }

    update_result = store.process_event(
        event_id="event-002",
        incident=second_incident,
        now=1793400002,
    )

    assert update_result == "UPDATED"

    incident_items = dynamodb.scan(
        TableName="test-incidents"
    )["Items"]

    processed_items = dynamodb.scan(
        TableName="test-processed-events"
    )["Items"]

    notification_items = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    assert len(incident_items) == 1
    assert incident_items[0]["event_count"]["N"] == "2"
    assert set(incident_items[0]["services"]["SS"]) == {
        "OrderService",
        "InventoryService",
    }

    assert len(processed_items) == 2
    assert len(notification_items) == 1



@mock_aws
def test_failed_transaction_does_not_save_partial_data():
    dynamodb = boto3.client("dynamodb", region_name="ap-south-1")

    tables = [
        ("test-incidents", "fingerprint"),
        ("test-processed-events", "event_id"),
        ("test-notification-outbox", "notification_id"),
    ]

    for table_name, key_name in tables:
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": key_name, "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": key_name, "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )

    store = DynamoDBIncidentStore(
        dynamodb_client=dynamodb,
        incident_table="test-incidents",
        processed_events_table="test-processed-events",
        notification_outbox_table="test-notification-outbox",
    )

    incident = {
        "fingerprint": "TIMEOUT:timeouterror",
        "category": "TIMEOUT",
        "severity": "HIGH",
        "services": ["OrderService"],
        "root_cause_hint": "Check dependency latency.",
    }

    dynamodb.put_item(
        TableName="test-notification-outbox",
        Item={
            "notification_id": {
                "S": "NEW#TIMEOUT:timeouterror#event-rollback"
            },
            "status": {"S": "PENDING"},
        },
    )

    with pytest.raises(ClientError):
        store.process_event(
            event_id="event-rollback",
            incident=incident,
            now=1793400000,
        )

    incidents = dynamodb.scan(
        TableName="test-incidents"
    )["Items"]

    processed_events = dynamodb.scan(
        TableName="test-processed-events"
    )["Items"]

    assert incidents == []
    assert processed_events == []


@mock_aws
def test_incident_resolves_after_two_missing_runs():
    dynamodb, store = create_test_store()
    incident = create_test_incident()

    result = store.process_event(
        event_id="recovery-event-001",
        incident=incident,
        now=1793400000,
    )

    assert result == "NEW"

    first_recovery = store.evaluate_recovery(
        active_fingerprints=set(),
    )

    assert first_recovery == []

    stored = dynamodb.get_item(
        TableName="test-incidents",
        Key={
            "fingerprint": {
                "S": "TIMEOUT:timeouterror"
            }
        },
    )["Item"]

    assert stored["status"]["S"] == "OPEN"
    assert stored["missing_runs"]["N"] == "1"

    second_recovery = store.evaluate_recovery(
        active_fingerprints=set(),
    )

    assert second_recovery == ["TIMEOUT:timeouterror"]

    outbox_items = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    recovery_notifications = [
        item
        for item in outbox_items
        if item.get("notification_type", {}).get("S")
        == "INCIDENT_RECOVERED"
    ]

    assert len(recovery_notifications) == 1

    notification = recovery_notifications[0]

    assert notification["status"]["S"] == "PENDING"
    assert notification["notification_type"]["S"] == "INCIDENT_RECOVERED"

    stored = dynamodb.get_item(
        TableName="test-incidents",
        Key={
            "fingerprint": {
                "S": "TIMEOUT:timeouterror"
            }
        },
    )["Item"]

    assert stored["status"]["S"] == "RESOLVED"
    assert stored["missing_runs"]["N"] == "2"

@mock_aws
def test_active_incident_resets_missing_runs():
    dynamodb, store = create_test_store()
    incident = create_test_incident()

    store.process_event(
        event_id="active-event-001",
        incident=incident,
        now=1793400000,
    )

    store.evaluate_recovery(active_fingerprints=set())

    active_result = store.evaluate_recovery(
        active_fingerprints={"TIMEOUT:timeouterror"},
    )

    assert active_result == []

    stored = dynamodb.get_item(
        TableName="test-incidents",
        Key={
            "fingerprint": {
                "S": "TIMEOUT:timeouterror"
            }
        },
    )["Item"]

    assert stored["status"]["S"] == "OPEN"
    assert stored["missing_runs"]["N"] == "0"


@mock_aws
def test_resolved_incident_is_not_processed_again():
    dynamodb, store = create_test_store()
    incident = create_test_incident()

    store.process_event(
        event_id="resolved-event-001",
        incident=incident,
        now=1793400000,
    )

    store.evaluate_recovery(active_fingerprints=set())
    resolved = store.evaluate_recovery(active_fingerprints=set())

    assert resolved == ["TIMEOUT:timeouterror"]

    third_recovery = store.evaluate_recovery(
        active_fingerprints=set(),
    )

    assert third_recovery == []

    stored = dynamodb.get_item(
        TableName="test-incidents",
        Key={
            "fingerprint": {
                "S": "TIMEOUT:timeouterror"
            }
        },
    )["Item"]

    assert stored["status"]["S"] == "RESOLVED"
    assert stored["missing_runs"]["N"] == "2"


@mock_aws
def test_recovery_threshold_must_be_at_least_one():
    _, store = create_test_store()

    with pytest.raises(
        ValueError,
        match="recovery_threshold must be at least 1",
    ):
        store.evaluate_recovery(
            active_fingerprints=set(),
            recovery_threshold=0,
        )



@mock_aws
def test_recovery_transaction_does_not_partially_update_incident(monkeypatch):
    dynamodb, store = create_test_store()
    incident = create_test_incident()

    fixed_uuid = UUID("12345678-1234-5678-1234-567812345678")

    monkeypatch.setattr(
        dynamodb_store,
        "uuid4",
        lambda: fixed_uuid,
    )

    store.process_event(
        event_id="rollback-recovery-001",
        incident=incident,
        now=1793400000,
    )

    store.evaluate_recovery(active_fingerprints=set())

    dynamodb.put_item(
        TableName="test-notification-outbox",
        Item={
            "notification_id": {
                "S": (
                    "RECOVERED#TIMEOUT:timeouterror#1793400000#"
                    "12345678-1234-5678-1234-567812345678"
                )
            },
            "status": {"S": "PENDING"},
        },
    )

    result = store.evaluate_recovery(
        active_fingerprints=set(),
    )

    assert result == []

    stored = dynamodb.get_item(
        TableName="test-incidents",
        Key={
            "fingerprint": {
                "S": "TIMEOUT:timeouterror"
            }
        },
    )["Item"]

    assert stored["status"]["S"] == "OPEN"
    assert stored["missing_runs"]["N"] == "1"



@mock_aws
def test_reopened_incident_gets_unique_recovery_notification():
    dynamodb, store = create_test_store()
    incident = create_test_incident()

    first_result = store.process_event(
        event_id="reopen-event-001",
        incident=incident,
        now=1793400000,
    )

    assert first_result == "NEW"

    first_recovery = store.evaluate_recovery(
        active_fingerprints=set(),
    )
    assert first_recovery == []

    second_recovery = store.evaluate_recovery(
        active_fingerprints=set(),
    )
    assert second_recovery == ["TIMEOUT:timeouterror"]

    first_notifications = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    first_recovery_ids = [
        item["notification_id"]["S"]
        for item in first_notifications
        if item.get("notification_type", {}).get("S")
        == "INCIDENT_RECOVERED"
    ]

    assert len(first_recovery_ids) == 1

    reopened_result = store.process_event(
        event_id="reopen-event-002",
        incident=incident,
        now=1793400000,
    )

    assert reopened_result == "UPDATED"

    reopened = dynamodb.get_item(
        TableName="test-incidents",
        Key={
            "fingerprint": {
                "S": "TIMEOUT:timeouterror"
            }
        },
    )["Item"]

    assert reopened["status"]["S"] == "OPEN"
    assert reopened["missing_runs"]["N"] == "0"

    store.evaluate_recovery(active_fingerprints=set())

    second_resolution = store.evaluate_recovery(
        active_fingerprints=set(),
    )

    assert second_resolution == ["TIMEOUT:timeouterror"]

    all_notifications = dynamodb.scan(
        TableName="test-notification-outbox"
    )["Items"]

    recovery_ids = [
        item["notification_id"]["S"]
        for item in all_notifications
        if item.get("notification_type", {}).get("S")
        == "INCIDENT_RECOVERED"
    ]

    assert len(recovery_ids) == 2
    assert len(set(recovery_ids)) == 2