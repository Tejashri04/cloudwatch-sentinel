"""Collect application log events from Amazon CloudWatch Logs."""

import json
from typing import Any

import boto3


def create_logs_client(region_name: str | None = None) -> Any:
    """Create a Boto3 CloudWatch Logs client."""
    return boto3.client("logs", region_name=region_name)


def fetch_log_events(
    client: Any,
    log_group_name: str,
    start_time_ms: int,
    end_time_ms: int,
    filter_pattern: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch log events from a CloudWatch log group."""

    if not log_group_name.strip():
        raise ValueError("Log group name cannot be empty")

    if start_time_ms > end_time_ms:
        raise ValueError("Start time must not be after end time")

    request: dict[str, Any] = {
        "logGroupName": log_group_name,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
    }

    if filter_pattern:
        request["filterPattern"] = filter_pattern

    events: list[dict[str, Any]] = []
    next_token = None

    while True:
        if next_token:
            request["nextToken"] = next_token

        response = client.filter_log_events(**request)

        events.extend(response.get("events", []))

        new_token = response.get("nextToken")

        if not new_token or new_token == next_token:
            break

        next_token = new_token

    return events

def parse_log_events(
    log_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert CloudWatch log messages into structured application events."""
    parsed_events = []

    for log_event in log_events:
        message = log_event.get("message", "")

        try:
            event = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(event, dict):
            parsed_events.append(event)

    return parsed_events
