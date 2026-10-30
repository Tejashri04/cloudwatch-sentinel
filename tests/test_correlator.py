"""Tests for incident correlation."""

from src.sentinel.correlator import correlate_events


def test_matching_errors_are_grouped_across_services():
    events = [
        {
            "service": "OrderService",
            "level": "ERROR",
            "message": "DynamoDB request timed out",
            "error_type": "TimeoutError",
        },
        {
            "service": "InventoryService",
            "level": "ERROR",
            "message": "Database request timed out",
            "error_type": "TimeoutError",
        },
        {
            "service": "NotificationService",
            "level": "ERROR",
            "message": "Request timed out",
            "error_type": "TimeoutError",
        },
    ]

    incidents = correlate_events(events)

    assert len(incidents) == 1

    incident = incidents[0]
    assert incident.category == "TIMEOUT"
    assert incident.severity == "HIGH"
    assert incident.event_count == 3
    assert incident.services == {
        "OrderService",
        "InventoryService",
        "NotificationService",
    }


def test_normal_events_are_ignored():
    events = [
        {
            "service": "OrderService",
            "level": "INFO",
            "message": "Order processed successfully",
        }
    ]

    incidents = correlate_events(events)

    assert incidents == []


def test_different_error_types_create_separate_groups():
    events = [
        {
            "service": "OrderService",
            "level": "ERROR",
            "message": "Request timed out",
            "error_type": "TimeoutError",
        },
        {
            "service": "InventoryService",
            "level": "ERROR",
            "message": "Access denied",
            "error_type": "AccessDeniedException",
        },
    ]

    incidents = correlate_events(events)

    assert len(incidents) == 2
    assert {incident.category for incident in incidents} == {
        "TIMEOUT",
        "PERMISSION",
    }
