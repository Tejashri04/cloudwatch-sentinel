import json

import boto3
from moto import mock_aws

from sentinel.notification_dispatcher import lambda_handler


def create_test_resources(monkeypatch):
    region = "ap-south-1"
    dynamodb = boto3.client("dynamodb", region_name=region)
    sns = boto3.client("sns", region_name=region)

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

    topic = sns.create_topic(Name="test-topic")

    monkeypatch.setenv(
        "NOTIFICATION_OUTBOX_TABLE",
        "test-notification-outbox",
    )
    monkeypatch.setenv("SNS_TOPIC_ARN", topic["TopicArn"])

    return dynamodb, sns, topic


def add_notification(
    dynamodb,
    notification_id,
    status="PENDING",
    attempts=0,
    notification_type="NEW_INCIDENT",
):
    dynamodb.put_item(
        TableName="test-notification-outbox",
        Item={
            "notification_id": {"S": notification_id},
            "fingerprint": {"S": "TIMEOUT:timeouterror"},
            "notification_type": {"S": notification_type},
            "status": {"S": status},
            "attempts": {"N": str(attempts)},
            "payload": {
                "S": json.dumps(
                    {
                        "fingerprint": "TIMEOUT:timeouterror",
                        "category": "TIMEOUT",
                        "severity": "HIGH",
                        "services": ["OrderService"],
                        "root_cause_hint": "Request timed out",
                    }
                )
            },
        },
    )


@mock_aws
def test_dispatcher_sends_pending_notification(monkeypatch):
    dynamodb, sns, topic = create_test_resources(monkeypatch)
    add_notification(dynamodb, "notification-001")

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=sns,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["pending_found"] == 1
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert result["skipped"] == 0

    stored = dynamodb.get_item(
        TableName="test-notification-outbox",
        Key={"notification_id": {"S": "notification-001"}},
    )["Item"]

    assert stored["status"]["S"] == "SENT"
    assert int(stored["attempts"]["N"]) == 1
    assert "sent_at" in stored
    assert "claim_token" not in stored
    assert "lease_until" not in stored

    topics = sns.list_topics()["Topics"]
    assert any(item["TopicArn"] == topic["TopicArn"] for item in topics)


@mock_aws
def test_dispatcher_does_not_resend_sent_notification(monkeypatch):
    dynamodb, sns, _ = create_test_resources(monkeypatch)
    add_notification(dynamodb, "notification-002", status="SENT", attempts=1)

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=sns,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["pending_found"] == 0
    assert result["sent"] == 0
    assert result["failed"] == 0


@mock_aws
def test_dispatcher_marks_notification_failed_after_retry_limit(monkeypatch):
    dynamodb, sns, _ = create_test_resources(monkeypatch)
    add_notification(
        dynamodb,
        "notification-003",
        status="PENDING",
        attempts=5,
    )

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=sns,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["failed"] == 1

    stored = dynamodb.get_item(
        TableName="test-notification-outbox",
        Key={"notification_id": {"S": "notification-003"}},
    )["Item"]

    assert stored["status"]["S"] == "FAILED"
    assert int(stored["attempts"]["N"]) == 5


@mock_aws
def test_dispatcher_skips_notification_claimed_by_another_invocation(
    monkeypatch,
):
    dynamodb, sns, _ = create_test_resources(monkeypatch)

    dynamodb.put_item(
        TableName="test-notification-outbox",
        Item={
            "notification_id": {"S": "notification-004"},
            "status": {"S": "PROCESSING"},
            "attempts": {"N": "1"},
            "claim_token": {"S": "existing-claim"},
            "lease_until": {"N": "9999999999"},
            "payload": {"S": "{}"},
        },
    )

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=sns,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["pending_found"] == 0
    assert result["sent"] == 0
    assert result["skipped"] == 0


@mock_aws
def test_dispatcher_retries_when_sns_publish_fails(monkeypatch):
    from botocore.exceptions import ClientError

    dynamodb, _, _ = create_test_resources(monkeypatch)
    add_notification(dynamodb, "notification-failure")

    class FailingSNSClient:
        def publish(self, **kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "InternalError",
                        "Message": "Simulated SNS failure",
                    }
                },
                "Publish",
            )

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=FailingSNSClient(),
    )

    result = json.loads(response["body"])

    stored = dynamodb.get_item(
        TableName="test-notification-outbox",
        Key={"notification_id": {"S": "notification-failure"}},
    )["Item"]

    assert response["statusCode"] == 200
    assert result["failed"] == 1
    assert stored["status"]["S"] == "PENDING"
    assert int(stored["attempts"]["N"]) == 1
    assert "claim_token" not in stored
    assert "lease_until" not in stored



@mock_aws
def test_dispatcher_recovers_expired_processing_lease(monkeypatch):
    dynamodb, sns, _ = create_test_resources(monkeypatch)

    dynamodb.put_item(
        TableName="test-notification-outbox",
        Item={
            "notification_id": {"S": "notification-expired-lease"},
            "fingerprint": {"S": "TIMEOUT:timeouterror"},
            "notification_type": {"S": "NEW_INCIDENT"},
            "status": {"S": "PROCESSING"},
            "attempts": {"N": "1"},
            "claim_token": {"S": "expired-claim"},
            "lease_until": {"N": "1"},
            "payload": {
                "S": json.dumps(
                    {
                        "fingerprint": "TIMEOUT:timeouterror",
                        "category": "TIMEOUT",
                        "severity": "HIGH",
                        "services": ["OrderService"],
                        "root_cause_hint": "Request timed out",
                    }
                )
            },
        },
    )

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=sns,
    )

    result = json.loads(response["body"])

    stored = dynamodb.get_item(
        TableName="test-notification-outbox",
        Key={
            "notification_id": {
                "S": "notification-expired-lease"
            }
        },
    )["Item"]

    assert response["statusCode"] == 200
    assert result["pending_found"] == 1
    assert result["sent"] == 1
    assert stored["status"]["S"] == "SENT"
    assert int(stored["attempts"]["N"]) == 2
    assert "claim_token" not in stored
    assert "lease_until" not in stored


@mock_aws
def test_dispatcher_processes_notifications_across_scan_pages(monkeypatch):
    dynamodb, sns, _ = create_test_resources(monkeypatch)

    for number in range(3):
        add_notification(
            dynamodb,
            f"notification-page-{number}",
        )

    original_scan = dynamodb.scan
    scan_calls = {"count": 0}

    def paginated_scan(**kwargs):
        scan_calls["count"] += 1

        if scan_calls["count"] == 1:
            response = original_scan(**kwargs)
            items = response.get("Items", [])

            if items:
                first_item = items[0]
                response["Items"] = [first_item]
                response["LastEvaluatedKey"] = {
                    "notification_id": first_item["notification_id"]
                }

            return response

        return original_scan(**kwargs)

    dynamodb.scan = paginated_scan

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=sns,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert scan_calls["count"] >= 2
    assert result["pending_found"] == 3
    assert result["sent"] == 3

    for number in range(3):
        stored = dynamodb.get_item(
            TableName="test-notification-outbox",
            Key={
                "notification_id": {
                    "S": f"notification-page-{number}"
                }
            },
        )["Item"]

        assert stored["status"]["S"] == "SENT"


@mock_aws
def test_dispatcher_sends_new_incident_subject(monkeypatch):
    dynamodb, sns, topic = create_test_resources(monkeypatch)
    add_notification(
        dynamodb,
        "notification-new",
        notification_type="NEW_INCIDENT",
    )

    published = []

    class RecordingSNSClient:
        def publish(self, **kwargs):
            published.append(kwargs)
            return sns.publish(**kwargs)

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=RecordingSNSClient(),
    )

    result = json.loads(response["body"])

    assert result["sent"] == 1
    assert published[0]["TopicArn"] == topic["TopicArn"]
    assert published[0]["Subject"] == (
        "CloudWatch Sentinel: New Incident"
    )


@mock_aws
def test_dispatcher_sends_recovery_subject(monkeypatch):
    dynamodb, sns, topic = create_test_resources(monkeypatch)
    add_notification(
        dynamodb,
        "notification-recovered",
        notification_type="INCIDENT_RECOVERED",
    )

    published = []

    class RecordingSNSClient:
        def publish(self, **kwargs):
            published.append(kwargs)
            return sns.publish(**kwargs)

    response = lambda_handler(
        {},
        None,
        dynamodb_client=dynamodb,
        sns_client=RecordingSNSClient(),
    )

    result = json.loads(response["body"])

    assert result["sent"] == 1
    assert published[0]["TopicArn"] == topic["TopicArn"]
    assert published[0]["Subject"] == (
        "CloudWatch Sentinel: Incident Recovered"
    )
