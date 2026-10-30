"""Manage incident state in a local JSON file."""

import json
from pathlib import Path
from typing import Any


class IncidentStateStore:
    """Persist incident state between local analysis runs."""

    def __init__(self, path: str = "incidents.json") -> None:
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, Any]]:
        """Load saved incidents, returning an empty store if none exists."""
        if not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(data, dict):
            return {}

        return {
            key: value
            for key, value in data.items()
            if isinstance(key, str) and isinstance(value, dict)
        }

    def save(self, incidents: dict[str, dict[str, Any]]) -> None:
        """Save incident state to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(incidents, indent=2),
            encoding="utf-8",
        )

    def update(
        self,
        active_fingerprints: set[str],
    ) -> dict[str, list[str]]:
        """Update incident states and report new, ongoing, and recovered items."""
        incidents = self.load()
        new: list[str] = []
        ongoing: list[str] = []
        recovered: list[str] = []

        for fingerprint in active_fingerprints:
            existing = incidents.get(fingerprint)

            if existing is None or existing.get("status") == "RESOLVED":
                incidents[fingerprint] = {"status": "OPEN"}
                new.append(fingerprint)
            else:
                ongoing.append(fingerprint)

        for fingerprint, incident in incidents.items():
            if (
                incident.get("status") == "OPEN"
                and fingerprint not in active_fingerprints
            ):
                incident["status"] = "RESOLVED"
                recovered.append(fingerprint)

        self.save(incidents)

        return {
            "new": sorted(new),
            "ongoing": sorted(ongoing),
            "recovered": sorted(recovered),
        }
