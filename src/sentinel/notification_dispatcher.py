"""Dispatch pending incident notifications from DynamoDB to SNS."""

import json
import logging
import os
import time
from typing import Any
from uuid import uuid4

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_ATTEMPTS = 5
CLAIM_LEASE_SECONDS = 120


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    dynamodb_client: Any = None,
    sns_client: Any = None,
) -> dict[str, Any]:
    """Publish pending outbox notifications to SNS."""

    outbox_table = os.environ.get("NOTIFICATION_OUTBOX_TABLE")
    topic_arn = os.environ.get("SNS_TOPIC_ARN")

    if not outbox_table or not topic_arn:
        raise ValueError(
            "NOTIFICATION_OUTBOX_TABLE and SNS_TOPIC_ARN "
            "environment variables are required"
        )

    if dynamodb_client is None:
        dynamodb_client = boto3.client("dynamodb")

    if sns_client is None:
        sns_client = boto3.client("sns")

    serializer = TypeSerializer()
    deserializer = TypeDeserializer()

    pending_items = []
    scan_kwargs = {
        "TableName": outbox_table,
        "FilterExpression": (
            "#status = :pending OR "
            "(#status = :processing AND lease_until < :now)"
        ),
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {
            ":pending": serializer.serialize("PENDING"),
            ":processing": serializer.serialize("PROCESSING"),
            ":now": serializer.serialize(int(time.time())),
        },
    }

    while True:
        response = dynamodb_client.scan(**scan_kwargs)
        pending_items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

        scan_kwargs["ExclusiveStartKey"] = last_key

    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for raw_item in pending_items:
        item = {
            key: deserializer.deserialize(value)
            for key, value in raw_item.items()
        }

        notification_id = item["notification_id"]
        attempts = int(item.get("attempts", 0))
        now = int(time.time())

        if attempts >= MAX_ATTEMPTS:
            try:
                dynamodb_client.update_item(
                    TableName=outbox_table,
                    Key={
                        "notification_id": serializer.serialize(
                            notification_id
                        )
                    },
                    UpdateExpression="SET #status = :failed",
                    ConditionExpression=(
                        "#status = :pending OR "
                        "(#status = :processing AND lease_until < :now)"
                    ),
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={
                        ":failed": serializer.serialize("FAILED"),
                        ":pending": serializer.serialize("PENDING"),
                        ":processing": serializer.serialize("PROCESSING"),
                        ":now": serializer.serialize(now),
                    },
                )
                failed_count += 1
            except ClientError as error:
                if error.response["Error"]["Code"] != (
                    "ConditionalCheckFailedException"
                ):
                    raise
                skipped_count += 1
            continue

        claim_token = str(uuid4())

        try:
            dynamodb_client.update_item(
                TableName=outbox_table,
                Key={
                    "notification_id": serializer.serialize(
                        notification_id
                    )
                },
                UpdateExpression=(
                    "SET #status = :processing, "
                    "claim_token = :token, lease_until = :lease, "
                    "updated_at = :now "
                    "ADD attempts :one"
                ),
                ConditionExpression=(
                    "#status = :pending OR "
                    "(#status = :processing AND lease_until < :now)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":pending": serializer.serialize("PENDING"),
                    ":processing": serializer.serialize("PROCESSING"),
                    ":token": serializer.serialize(claim_token),
                    ":lease": serializer.serialize(
                        now + CLAIM_LEASE_SECONDS
                    ),
                    ":now": serializer.serialize(now),
                    ":one": serializer.serialize(1),
                },
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == (
                "ConditionalCheckFailedException"
            ):
                skipped_count += 1
                continue
            raise

        try:
            notification_type = item.get(
                "notification_type",
                "NEW_INCIDENT",
            )

            if notification_type == "INCIDENT_RECOVERED":
                subject = "CloudWatch Sentinel: Incident Recovered"
            elif notification_type == "NEW_INCIDENT":
                subject = "CloudWatch Sentinel: New Incident"
            else:
                raise ValueError(
                    f"Unsupported notification type: {notification_type}"
                )

            payload = json.loads(item["payload"])

            sns_client.publish(
                TopicArn=topic_arn,
                Subject=subject,
                Message=json.dumps(payload),
            )

            dynamodb_client.update_item(
                TableName=outbox_table,
                Key={
                    "notification_id": serializer.serialize(
                        notification_id
                    )
                },
                UpdateExpression=(
                    "SET #status = :sent, sent_at = :now "
                    "REMOVE claim_token, lease_until"
                ),
                ConditionExpression=(
                    "#status = :processing AND claim_token = :token"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":sent": serializer.serialize("SENT"),
                    ":processing": serializer.serialize("PROCESSING"),
                    ":token": serializer.serialize(claim_token),
                    ":now": serializer.serialize(int(time.time())),
                },
            )

            sent_count += 1

        except (ClientError, ValueError, KeyError, TypeError):
            logger.exception(
                "Failed to dispatch notification %s",
                notification_id,
            )

            try:
                dynamodb_client.update_item(
                    TableName=outbox_table,
                    Key={
                        "notification_id": serializer.serialize(
                            notification_id
                        )
                    },
                    UpdateExpression=(
                        "SET #status = :pending "
                        "REMOVE claim_token, lease_until"
                    ),
                    ConditionExpression=(
                        "#status = :processing AND claim_token = :token"
                    ),
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={
                        ":pending": serializer.serialize("PENDING"),
                        ":processing": serializer.serialize("PROCESSING"),
                        ":token": serializer.serialize(claim_token),
                    },
                )
            except ClientError:
                logger.exception(
                    "Could not release notification claim for %s",
                    notification_id,
                )

            failed_count += 1

    logger.info(
        "Notification dispatch finished: sent=%s failed=%s skipped=%s",
        sent_count,
        failed_count,
        skipped_count,
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "pending_found": len(pending_items),
                "sent": sent_count,
                "failed": failed_count,
                "skipped": skipped_count,
            }
        ),
    }