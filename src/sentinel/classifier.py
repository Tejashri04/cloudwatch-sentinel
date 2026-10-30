"""Classify application log events for CloudWatch Sentinel."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Classification:
    """Structured result of classifying a log event."""

    severity: str
    category: str
    fingerprint: str
    root_cause_hint: str


def classify_event(event: dict[str, Any]) -> Classification:
    """Classify a structured application log event.

    Expected fields may include:
        service: Name of the application service.
        level: Log level, such as INFO, WARNING, or ERROR.
        message: Description of the event.
        error_type: Exception or error name.
        dependency: External dependency involved, if any.
    """
    level = str(event.get("level", "INFO")).upper()
    message = str(event.get("message", ""))
    error_type = str(event.get("error_type", ""))
    dependency = str(event.get("dependency", ""))

    searchable_text = f"{message} {error_type} {dependency}".lower()

    if any(
        term in searchable_text
        for term in ("throttl", "rate exceeded", "too many requests")
    ):
        category = "THROTTLING"
        hint = "Check service quotas, request rates, and retry behavior."

    elif any(
        term in searchable_text
        for term in ("timeout", "timed out", "deadline exceeded")
    ):
        category = "TIMEOUT"
        hint = "Check dependency latency, network delays, and timeout settings."

    elif any(
        term in searchable_text
        for term in ("accessdenied", "access denied", "unauthorized", "forbidden")
    ):
        category = "PERMISSION"
        hint = "Check IAM permissions, resource policies, and credentials."

    elif any(
        term in searchable_text
        for term in ("connection refused", "connection reset", "unreachable")
    ):
        category = "CONNECTIVITY"
        hint = "Check network connectivity, endpoints, and service availability."

    elif any(
        term in searchable_text
        for term in ("resource not found", "does not exist", "notfound")
    ):
        category = "RESOURCE_NOT_FOUND"
        hint = "Check resource names, identifiers, regions, and deployment state."

    elif level in {"ERROR", "CRITICAL", "FATAL"}:
        category = "APPLICATION_ERROR"
        hint = "Inspect the exception details and the surrounding application logs."

    elif level == "WARNING":
        category = "WARNING"
        hint = "Review the event and determine whether it needs investigation."

    else:
        category = "NORMAL"
        hint = "No immediate action indicated by this event."


    if level in {"CRITICAL", "FATAL"}:
        severity = "CRITICAL"
    elif level == "ERROR" or category in {
        "THROTTLING",
        "TIMEOUT",
        "PERMISSION",
        "CONNECTIVITY",
    }:
        severity = "HIGH"
    elif level == "WARNING":
        severity = "MEDIUM"
    else:
        severity = "LOW"

    # Group related errors by category and error type.
    # Service is deliberately excluded so errors from different services
    # can potentially be correlated later.
    fingerprint_source = error_type.strip().lower() or category.lower()
    fingerprint = f"{category}:{fingerprint_source}"

    return Classification(
        severity=severity,
        category=category,
        fingerprint=fingerprint,
        root_cause_hint=hint,
    )