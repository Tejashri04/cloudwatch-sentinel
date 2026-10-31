"""Run incident detection using AWS CloudWatch logs."""

import time

from src.sentinel.alert_manager import AlertManager
from src.sentinel.cloudwatch import (
    create_logs_client,
    fetch_log_events,
    parse_log_events,
)
from src.sentinel.correlator import correlate_events
from src.sentinel.state import IncidentStateStore

REGION = "ap-south-1"
LOG_GROUP = "/cloudwatch-sentinel/application"
STATE_FILE = "data/incidents.json"


def main():
    client = create_logs_client(REGION)

    LOOKBACK_HOURS = 24

    end_time = int(time.time() * 1000)
    start_time = end_time - (LOOKBACK_HOURS * 60 * 60 * 1000)

    print("Connecting to AWS CloudWatch...")
    print(f"Reading logs from: {LOG_GROUP}")

    raw_events = fetch_log_events(
        client,
        LOG_GROUP,
        start_time,
        end_time,
    )

    events = parse_log_events(raw_events)

    print(f"\nTotal CloudWatch log events fetched: {len(raw_events)}")
    print(f"Valid structured events: {len(events)}")

    incidents = correlate_events(events)

    store = IncidentStateStore(STATE_FILE)
    alert_manager = AlertManager(store)

    active_fingerprints = [
        incident.fingerprint for incident in incidents
    ]

    alert_updates = alert_manager.evaluate(active_fingerprints)

    print("\n========== INCIDENT ANALYSIS ==========")

    if not incidents:
        print("No active incidents detected.")

    for incident in incidents:
        print(f"\nCategory: {incident.category}")
        print(f"Severity: {incident.severity}")
        print(f"Fingerprint: {incident.fingerprint}")
        print(f"Affected services: {', '.join(sorted(incident.services))}")
        print(f"Event count: {incident.event_count}")
        print(f"Root cause hint: {incident.root_cause_hint}")

    print("\n========== ALERT STATUS ==========")
    print(alert_updates)

    print("\nIncident analysis completed.")


if __name__ == "__main__":
    main()