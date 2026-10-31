
from unittest.mock import MagicMock, patch

import pytest

from src.sentinel.cloudwatch import (
    create_logs_client,
    fetch_log_events,
    parse_log_events,
)


def test_create_logs_client():
    with patch("src.sentinel.cloudwatch.boto3.client") as mock_client:
        create_logs_client("ap-south-1")

        mock_client.assert_called_once_with(
            "logs",
            region_name="ap-south-1",
        )


def test_fetch_log_events():
    mock_client = MagicMock()
    mock_client.filter_log_events.return_value = {
        "events": [{"message": "Test log event"}]
    }

    result = fetch_log_events(
        mock_client,
        "/cloudwatch-sentinel/application",
        1000,
        2000,
    )

    assert len(result) == 1
    assert result[0]["message"] == "Test log event"


def test_fetch_log_events_pagination():
    mock_client = MagicMock()
    mock_client.filter_log_events.side_effect = [
        {
            "events": [{"message": "First event"}],
            "nextToken": "token-1",
        },
        {
            "events": [{"message": "Second event"}],
            "nextToken": "token-2",
        },
        {
            "events": [{"message": "Third event"}],
        },
    ]

    result = fetch_log_events(
        mock_client,
        "/cloudwatch-sentinel/application",
        1000,
        3000,
    )

    assert len(result) == 3
    assert mock_client.filter_log_events.call_count == 3


def test_fetch_log_events_empty_log_group():
    mock_client = MagicMock()

    with pytest.raises(ValueError, match="Log group name cannot be empty"):
        fetch_log_events(mock_client, " ", 1000, 2000)


def test_fetch_log_events_invalid_time_range():
    mock_client = MagicMock()

    with pytest.raises(
        ValueError,
        match="Start time must not be after end time",
    ):
        fetch_log_events(
            mock_client,
            "/cloudwatch-sentinel/application",
            3000,
            2000,
        )


def test_fetch_log_events_with_filter_pattern():
    mock_client = MagicMock()
    mock_client.filter_log_events.return_value = {
        "events": [{"message": "Error event"}]
    }

    fetch_log_events(
        mock_client,
        "/cloudwatch-sentinel/application",
        1000,
        2000,
        filter_pattern="ERROR",
    )

    mock_client.filter_log_events.assert_called_once_with(
        logGroupName="/cloudwatch-sentinel/application",
        startTime=1000,
        endTime=2000,
        filterPattern="ERROR",
    )


def test_parse_log_events():
    log_events = [
        {
            "message": (
                '{"service": "OrderService", '
                '"level": "ERROR", '
                '"message": "DynamoDB request timed out", '
                '"error_type": "TimeoutError"}'
            )
        }
    ]

    result = parse_log_events(log_events)

    assert len(result) == 1
    assert result[0]["service"] == "OrderService"
    assert result[0]["level"] == "ERROR"
    assert result[0]["error_type"] == "TimeoutError"


def test_parse_log_events_skips_invalid_json():
    log_events = [
        {"message": "This is not valid JSON"},
        {"message": '{"service": "PaymentService", "level": "ERROR"}'},
    ]

    result = parse_log_events(log_events)

    assert len(result) == 1
    assert result[0]["service"] == "PaymentService"
