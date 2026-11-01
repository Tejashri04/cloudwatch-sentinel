"""Group related classified events into incidents."""

from dataclasses import dataclass, field
from typing import Any

from sentinel.classifier import Classification, classify_event


@dataclass
class Incident:
    """A group of related errors that may share a common cause."""

    fingerprint: str
    category: str
    severity: str
    services: set[str] = field(default_factory=set)
    event_count: int = 0
    root_cause_hint: str = ""


def correlate_events(events: list[dict[str, Any]]) -> list[Incident]:
    """Group events that have the same classification fingerprint.

    This is a first prototype. Matching fingerprints indicate potentially
    related errors, not proof that the underlying cause is identical.
    """
    incidents: dict[str, Incident] = {}

    for event in events:
        result: Classification = classify_event(event)

        # Ignore normal events; only investigate noteworthy events.
        if result.severity == "LOW":
            continue

        fingerprint = result.fingerprint
        service = str(event.get("service", "unknown"))

        if fingerprint not in incidents:
            incidents[fingerprint] = Incident(
                fingerprint=fingerprint,
                category=result.category,
                severity=result.severity,
                root_cause_hint=result.root_cause_hint,
            )

        incident = incidents[fingerprint]
        incident.services.add(service)
        incident.event_count += 1

        # Keep the highest severity if events in the group differ.
        severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

        if severity_rank[result.severity] > severity_rank[incident.severity]:
            incident.severity = result.severity

    return list(incidents.values())
