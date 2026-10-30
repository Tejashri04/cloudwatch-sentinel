"""Run a local demonstration of CloudWatch Sentinel."""

from src.sentinel.correlator import correlate_events
from src.sentinel.state import IncidentStateStore


def main() -> None:
    """Analyze sample logs and track incident lifecycle."""
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
            "message": "DynamoDB request timed out",
            "error_type": "TimeoutError",
        },
        {
            "service": "NotificationService",
            "level": "ERROR",
            "message": "Request timed out while sending notification",
            "error_type": "TimeoutError",
        },
        {
            "service": "PaymentService",
            "level": "ERROR",
            "message": "Access denied when calling payment API",
            "error_type": "AccessDeniedException",
        },
        {
            "service": "OrderService",
            "level": "INFO",
            "message": "Order processed successfully",
        },
    ]

    incidents = correlate_events(events)

    # Keep local state in a separate directory.
    store = IncidentStateStore("data/incidents.json")
    active_fingerprints = {incident.fingerprint for incident in incidents}
    changes = store.update(active_fingerprints)

    print("=" * 60)
    print("CLOUDWATCH SENTINEL - INCIDENT ANALYSIS")
    print("=" * 60)
    print(f"Events analyzed: {len(events)}")
    print(f"Incidents detected: {len(incidents)}")
    print(f"New incidents: {len(changes['new'])}")
    print(f"Ongoing incidents: {len(changes['ongoing'])}")
    print(f"Recovered incidents: {len(changes['recovered'])}")
    print()

    for incident in incidents:
        if incident.fingerprint in changes["new"]:
            status = "NEW"
        else:
            status = "ONGOING"

        print(f"[{status}] {incident.category} - {incident.severity}")
        print(f"  Fingerprint: {incident.fingerprint}")
        print(f"  Events: {incident.event_count}")
        print(f"  Services: {', '.join(sorted(incident.services))}")
        print(f"  Hint: {incident.root_cause_hint}")
        print()

    if changes["recovered"]:
        print("Recovered incidents:")
        for fingerprint in changes["recovered"]:
            print(f"  - {fingerprint}")

    print("=" * 60)
    print("Analysis complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
