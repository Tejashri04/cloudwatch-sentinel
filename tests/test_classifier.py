"""Tests for the CloudWatch Sentinel classifier."""

from src.sentinel.classifier import classify_event


def test_timeout_error_is_classified_as_high_severity():
    event = {
        "service": "OrderService",
        "level": "ERROR",
        "message": "Request timed out while calling DynamoDB",
        "error_type": "TimeoutError",
        "dependency": "DynamoDB",
    }

    result = classify_event(event)

    assert result.severity == "HIGH"
    assert result.category == "TIMEOUT"
    assert "latency" in result.root_cause_hint.lower()


def test_permission_error_is_detected():
    event = {
        "service": "InventoryService",
        "level": "ERROR",
        "message": "AccessDenied: operation not allowed",
        "error_type": "AccessDeniedException",
    }

    result = classify_event(event)

    assert result.category == "PERMISSION"
    assert result.severity == "HIGH"


def test_critical_event_has_critical_severity():
    event = {
        "service": "PaymentService",
        "level": "CRITICAL",
        "message": "Payment processing has failed",
    }

    result = classify_event(event)

    assert result.severity == "CRITICAL"
    assert result.category == "APPLICATION_ERROR"


def test_info_event_is_normal():
    event = {
        "service": "NotificationService",
        "level": "INFO",
        "message": "Notification sent successfully",
    }

    result = classify_event(event)

    assert result.severity == "LOW"
    assert result.category == "NORMAL"


def test_same_error_type_can_be_grouped_across_services():
    order_event = {
        "service": "OrderService",
        "level": "ERROR",
        "message": "Request timed out",
        "error_type": "TimeoutError",
    }

    inventory_event = {
        "service": "InventoryService",
        "level": "ERROR",
        "message": "Database request timed out",
        "error_type": "TimeoutError",
    }

    order_result = classify_event(order_event)
    inventory_result = classify_event(inventory_event)

    assert order_result.fingerprint == inventory_result.fingerprint
