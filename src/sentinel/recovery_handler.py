
"""Scheduled Lambda handler for evaluating incident recovery."""

import json
import logging
import os
import time
from typing import Any

import boto3

from sentinel.cloudwatch import fetch_log_events, parse_log_events
from sentinel.correlator import correlate_events
from sentinel.dynamodb_store import DynamoDBIncidentStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

LOOKBACK_HOURS = 23
RECOVERY_THRESHOLD = 2
HEARTBEAT_MAX_AGE_MINUTES = 15


def has_recent_heartbeat(
    log_events: list[dict[str, Any]],
    now_ms: int,
) -> bool:
    """Check whether CloudWatch contains a recent application heartbeat."""

    minimum_timestamp = (
        now_ms - HEARTBEAT_MAX_AGE_MINUTES * 60 * 1000
    )

    for log_event in log_events:
        try:
            event = json.loads(log_event.get("message", ""))
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(event, dict):
            continue

        if event.get("event_type") != "HEARTBEAT":
            continue

        timestamp = log_event.get("timestamp")

        if (
            isinstance(timestamp, (int, float))
            and minimum_timestamp <= timestamp <= now_ms
        ):
            return True

    return False


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    logs_client: Any = None,
    dynamodb_client: Any = None,
) -> dict[str, Any]:
    """Evaluate whether previously detected incidents have recovered."""

    log_group_name = os.environ.get("APPLICATION_LOG_GROUP")
    incident_table = os.environ.get("INCIDENT_TABLE")
    processed_events_table = os.environ.get("PROCESSED_EVENTS_TABLE")
    notification_outbox_table = os.environ.get(
        "NOTIFICATION_OUTBOX_TABLE"
    )

    if not all(
        [
            log_group_name,
            incident_table,
            processed_events_table,
            notification_outbox_table,
        ]
    ):
        raise ValueError(
            "APPLICATION_LOG_GROUP, INCIDENT_TABLE, "
            "PROCESSED_EVENTS_TABLE and NOTIFICATION_OUTBOX_TABLE "
            "environment variables are required"
        )

    if logs_client is None:
        logs_client = boto3.client("logs")

    if dynamodb_client is None:
        dynamodb_client = boto3.client("dynamodb")

    now_ms = int(time.time() * 1000)
    start_time_ms = now_ms - LOOKBACK_HOURS * 60 * 60 * 1000

    log_events = fetch_log_events(
        client=logs_client,
        log_group_name=log_group_name,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
    )

    if not has_recent_heartbeat(log_events, now_ms):
        logger.warning(
            "Recovery evaluation skipped: no recent application heartbeat"
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "recovery_skipped": True,
                "reason": "No recent application heartbeat",
                "logs_fetched": len(log_events),
            }),
        }

    parsed_events = parse_log_events(log_events)

    if not parsed_events:
        logger.warning(
            "Recovery evaluation skipped: no usable CloudWatch logs found"
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "recovery_skipped": True,
                "reason": "No usable CloudWatch logs found",
                "logs_fetched": len(log_events),
                "valid_events": 0,
            }),
        }

    incidents = correlate_events(parsed_events)

    active_fingerprints = {
        incident.fingerprint for incident in incidents
    }

    store = DynamoDBIncidentStore(
        dynamodb_client=dynamodb_client,
        incident_table=incident_table,
        processed_events_table=processed_events_table,
        notification_outbox_table=notification_outbox_table,
    )

    resolved = store.evaluate_recovery(
        active_fingerprints=active_fingerprints,
        recovery_threshold=RECOVERY_THRESHOLD,
    )

    result = {
        "logs_fetched": len(log_events),
        "valid_events": len(parsed_events),
        "active_incidents": len(active_fingerprints),
        "resolved_incidents": resolved,
    }

    logger.info("Recovery evaluation completed: %s", result)

    return {
        "statusCode": 200,
        "body": json.dumps(result),
    }
