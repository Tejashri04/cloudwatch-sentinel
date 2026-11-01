"""AWS Lambda handler for CloudWatch Sentinel."""

import base64
import gzip
import json
import logging
import os

import boto3

from sentinel.correlator import correlate_events
from sentinel.dynamodb_store import DynamoDBIncidentStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context, dynamodb_client=None):
    """Process CloudWatch Logs subscription events."""

    compressed_data = base64.b64decode(event["awslogs"]["data"])
    payload = json.loads(gzip.decompress(compressed_data))

    if payload.get("messageType") == "CONTROL_MESSAGE":
        return {
            "statusCode": 200,
            "body": "Control message received",
        }

    incident_table = os.environ.get("INCIDENT_TABLE")
    processed_events_table = os.environ.get("PROCESSED_EVENTS_TABLE")
    notification_outbox_table = os.environ.get(
        "NOTIFICATION_OUTBOX_TABLE"
    )

    if not all(
        [
            incident_table,
            processed_events_table,
            notification_outbox_table,
        ]
    ):
        raise ValueError(
            "INCIDENT_TABLE, PROCESSED_EVENTS_TABLE and "
            "NOTIFICATION_OUTBOX_TABLE environment variables are required"
        )

    if dynamodb_client is None:
        dynamodb_client = boto3.client("dynamodb")

    store = DynamoDBIncidentStore(
        dynamodb_client=dynamodb_client,
        incident_table=incident_table,
        processed_events_table=processed_events_table,
        notification_outbox_table=notification_outbox_table,
    )

    processed_events = 0
    duplicate_events = 0
    skipped_events = 0
    new_incidents = 0
    updated_incidents = 0

    for log_event in payload.get("logEvents", []):
        event_id = log_event.get("id")
        message = log_event.get("message")

        if not event_id or not isinstance(message, str):
            logger.warning("Skipping log event with missing ID or message")
            skipped_events += 1
            continue

        try:
            parsed_event = json.loads(message)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON log event: %s", event_id)
            skipped_events += 1
            continue

        if not isinstance(parsed_event, dict):
            logger.debug("Skipping non-object JSON event: %s", event_id)
            skipped_events += 1
            continue

        incidents = correlate_events([parsed_event])

        if not incidents:
            skipped_events += 1
            continue

        for incident in incidents:
            incident_data = {
                "fingerprint": incident.fingerprint,
                "category": incident.category,
                "severity": incident.severity,
                "services": sorted(incident.services),
                "root_cause_hint": incident.root_cause_hint,
            }

            result = store.process_event(
                event_id=event_id,
                incident=incident_data,
            )

            if result == "DUPLICATE":
                duplicate_events += 1
            elif result == "NEW":
                processed_events += 1
                new_incidents += 1
            elif result == "UPDATED":
                processed_events += 1
                updated_incidents += 1

    logger.info(
        "Processed %s events, skipped %s duplicates, "
        "created %s incidents, updated %s incidents, "
        "and skipped %s non-incident events",
        processed_events,
        duplicate_events,
        new_incidents,
        updated_incidents,
        skipped_events,
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "processed_events": processed_events,
                "duplicate_events": duplicate_events,
                "detected_incidents": (
                    new_incidents + updated_incidents
                ),
                "new_incidents": new_incidents,
                "updated_incidents": updated_incidents,
                "skipped_events": skipped_events,
            }
        ),
    }