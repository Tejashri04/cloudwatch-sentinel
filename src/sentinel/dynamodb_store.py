
"""Manage incident data using atomic DynamoDB transactions."""

import json
import time
from typing import Any
from uuid import uuid4

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError


class DynamoDBIncidentStore:
    """Store incidents and prevent duplicate event processing."""

    def __init__(
        self,
        dynamodb_client: Any,
        incident_table: str,
        processed_events_table: str,
        notification_outbox_table: str,
    ) -> None:
        self.client = dynamodb_client
        self.incident_table = incident_table
        self.processed_events_table = processed_events_table
        self.notification_outbox_table = notification_outbox_table
        self.serializer = TypeSerializer()

    def _serialize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Convert a Python dictionary into DynamoDB format."""
        return {
            key: self.serializer.serialize(value)
            for key, value in item.items()
        }

    def _event_exists(self, event_id: str) -> bool:
        """Check whether an event has already been processed."""
        response = self.client.get_item(
            TableName=self.processed_events_table,
            Key={
                "event_id": self.serializer.serialize(event_id),
            },
            ConsistentRead=True,
        )
        return "Item" in response

    def process_event(
        self,
        event_id: str,
        incident: dict[str, Any],
        now: int | None = None,
    ) -> str:
        """Atomically record an event and update its incident."""

        if now is None:
            now = int(time.time())

        fingerprint = incident["fingerprint"]
        services = set(incident.get("services", []))

        event_item = {
            "event_id": event_id,
            "expires_at": now + 604800,
        }

        incident_item = {
            "fingerprint": fingerprint,
            "category": incident["category"],
            "severity": incident["severity"],
            "services": services,
            "event_count": 1,
            "root_cause_hint": incident["root_cause_hint"],
            "status": "OPEN",
            "missing_runs": 0,
            "first_seen": now,
            "last_seen": now,
        }

        notification_id = f"NEW#{fingerprint}#{event_id}"

        notification_item = {
            "notification_id": notification_id,
            "fingerprint": fingerprint,
            "notification_type": "NEW_INCIDENT",
            "status": "PENDING",
            "attempts": 0,
            "created_at": now,
            "payload": json.dumps({
                "fingerprint": fingerprint,
                "category": incident["category"],
                "severity": incident["severity"],
                "services": sorted(services),
                "root_cause_hint": incident["root_cause_hint"],
            }),
        }

        new_incident_transaction = [
            {
                "Put": {
                    "TableName": self.processed_events_table,
                    "Item": self._serialize_item(event_item),
                    "ConditionExpression": "attribute_not_exists(event_id)",
                }
            },
            {
                "Put": {
                    "TableName": self.incident_table,
                    "Item": self._serialize_item(incident_item),
                    "ConditionExpression": (
                        "attribute_not_exists(fingerprint)"
                    ),
                }
            },
            {
                "Put": {
                    "TableName": self.notification_outbox_table,
                    "Item": self._serialize_item(notification_item),
                    "ConditionExpression": (
                        "attribute_not_exists(notification_id)"
                    ),
                }
            },
        ]

        try:
            self.client.transact_write_items(
                TransactItems=new_incident_transaction
            )
            return "NEW"

        except ClientError as error:
            if (
                error.response["Error"]["Code"]
                != "TransactionCanceledException"
            ):
                raise

        if self._event_exists(event_id):
            return "DUPLICATE"

        existing_incident_transaction = [
            {
                "Put": {
                    "TableName": self.processed_events_table,
                    "Item": self._serialize_item(event_item),
                    "ConditionExpression": "attribute_not_exists(event_id)",
                }
            },
            {
                "Update": {
                    "TableName": self.incident_table,
                    "Key": {
                        "fingerprint": self.serializer.serialize(fingerprint),
                    },
                    "UpdateExpression": (
                        "SET #status = :status, last_seen = :now, missing_runs = :zero "
                        "ADD event_count :one, services :services"
                    ),
                    "ConditionExpression": "attribute_exists(fingerprint)",
                    "ExpressionAttributeNames": {
                        "#status": "status",
                    },
                    "ExpressionAttributeValues": {
                        ":status": self.serializer.serialize("OPEN"),
                        ":now": self.serializer.serialize(now),
                        ":zero": self.serializer.serialize(0),
                        ":one": self.serializer.serialize(1),
                        ":services": self.serializer.serialize(services),
                    },
                }
            },
        ]

        try:
            self.client.transact_write_items(
                TransactItems=existing_incident_transaction
            )
            return "UPDATED"

        except ClientError as error:
            if (
                error.response["Error"]["Code"]
                != "TransactionCanceledException"
            ):
                raise

            if self._event_exists(event_id):
                return "DUPLICATE"

            raise

    def _build_recovery_notification(
        self,
        fingerprint: str,
        incident: dict[str, Any],
        now: int,
    ) -> dict[str, Any]:
        """Build a recovery notification for the outbox."""

        notification_id = (
            f"RECOVERED#{fingerprint}#"
            f"{incident.get('last_seen', now)}#{uuid4()}"
        )

        return {
            "notification_id": notification_id,
            "fingerprint": fingerprint,
            "notification_type": "INCIDENT_RECOVERED",
            "status": "PENDING",
            "attempts": 0,
            "created_at": now,
            "payload": json.dumps({
                "fingerprint": fingerprint,
                "category": incident.get("category", "UNKNOWN"),
                "severity": incident.get("severity", "UNKNOWN"),
                "services": sorted(
                    incident.get("services", [])
                ),
                "root_cause_hint": incident.get(
                    "root_cause_hint",
                    "",
                ),
            }),
        }


    def evaluate_recovery(
        self,
        active_fingerprints: set[str],
        recovery_threshold: int = 2,
    ) -> list[str]:
        """Resolve incidents after repeated absence from analysis."""

        if recovery_threshold < 1:
            raise ValueError("recovery_threshold must be at least 1")

        resolved: list[str] = []
        last_key = None

        while True:
            scan_kwargs = {
                "TableName": self.incident_table,
                "ProjectionExpression": (
                    "fingerprint, #status, missing_runs, last_seen, "
                    "category, severity, services, root_cause_hint"
                ),
                "ExpressionAttributeNames": {
                    "#status": "status",
                },
            }

            if last_key:
                scan_kwargs["ExclusiveStartKey"] = last_key

            response = self.client.scan(**scan_kwargs)

            for item in response.get("Items", []):
                fingerprint = item["fingerprint"]["S"]
                status = item.get("status", {}).get("S", "OPEN")

                if status != "OPEN":
                    continue

                if fingerprint in active_fingerprints:
                    self.client.update_item(
                        TableName=self.incident_table,
                        Key={
                            "fingerprint": self.serializer.serialize(
                                fingerprint
                            ),
                        },
                        UpdateExpression="SET missing_runs = :zero",
                        ExpressionAttributeValues={
                            ":zero": self.serializer.serialize(0),
                            ":open": self.serializer.serialize("OPEN"),
                        },
                        ConditionExpression="#status = :open",
                        ExpressionAttributeNames={
                            "#status": "status",
                        },
                    )
                    continue

                missing_runs = int(
                    item.get("missing_runs", {}).get("N", "0")
                ) + 1

                if missing_runs >= recovery_threshold:
                    incident_details = {
                        "category": item.get(
                            "category", {}
                        ).get("S", "UNKNOWN"),
                        "severity": item.get(
                            "severity", {}
                        ).get("S", "UNKNOWN"),
                        "services": item.get(
                            "services", {}
                        ).get("SS", []),
                        "root_cause_hint": item.get(
                            "root_cause_hint", {}
                        ).get("S", ""),
                        "last_seen": int(
                            item.get("last_seen", {}).get("N", "0")
                        ),
                    }

                    notification = self._build_recovery_notification(
                        fingerprint=fingerprint,
                        incident=incident_details,
                        now=int(time.time()),
                    )

                    try:
                        self.client.transact_write_items(
                            TransactItems=[
                                {
                                    "Update": {
                                        "TableName": self.incident_table,
                                        "Key": {
                                            "fingerprint": (
                                                self.serializer.serialize(
                                                    fingerprint
                                                )
                                            ),
                                        },
                                        "UpdateExpression": (
                                            "SET #status = :resolved, "
                                            "missing_runs = :count"
                                        ),
                                        "ConditionExpression": (
                                            "#status = :open "
                                            "AND last_seen = :last_seen "
                                            "AND missing_runs = :previous"
                                        ),
                                        "ExpressionAttributeNames": {
                                            "#status": "status",
                                        },
                                        "ExpressionAttributeValues": {
                                            ":resolved": (
                                                self.serializer.serialize(
                                                    "RESOLVED"
                                                )
                                            ),
                                            ":count": (
                                                self.serializer.serialize(
                                                    missing_runs
                                                )
                                            ),
                                            ":open": (
                                                self.serializer.serialize(
                                                    "OPEN"
                                                )
                                            ),
                                            ":last_seen": (
                                                self.serializer.serialize(
                                                    incident_details[
                                                        "last_seen"
                                                    ]
                                                )
                                            ),
                                            ":previous": (
                                                self.serializer.serialize(
                                                    missing_runs - 1
                                                )
                                            ),
                                        },
                                    }
                                },
                                {
                                    "Put": {
                                        "TableName": (
                                            self.notification_outbox_table
                                        ),
                                        "Item": self._serialize_item(
                                            notification
                                        ),
                                        "ConditionExpression": (
                                            "attribute_not_exists("
                                            "notification_id)"
                                        ),
                                    }
                                },
                            ]
                        )

                        resolved.append(fingerprint)

                    except ClientError as error:
                        if (
                            error.response["Error"]["Code"]
                            != "TransactionCanceledException"
                        ):
                            raise
                else:
                    self.client.update_item(
                        TableName=self.incident_table,
                        Key={
                            "fingerprint": self.serializer.serialize(
                                fingerprint
                            ),
                        },
                        UpdateExpression="SET missing_runs = :count",
                        ConditionExpression=(
                            "#status = :open "
                            "AND last_seen = :last_seen "
                            "AND missing_runs = :previous"
                        ),
                        ExpressionAttributeNames={
                            "#status": "status",
                        },
                        ExpressionAttributeValues={
                            ":count": self.serializer.serialize(
                                missing_runs
                            ),
                            ":open": self.serializer.serialize("OPEN"),
                            ":last_seen": self.serializer.serialize(
                                int(item.get("last_seen", {}).get("N", "0"))
                            ),
                            ":previous": self.serializer.serialize(
                                missing_runs - 1
                            ),
                        },
                    )

            last_key = response.get("LastEvaluatedKey")

            if not last_key:
                break

        return sorted(resolved)