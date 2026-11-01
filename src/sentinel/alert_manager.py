"""Manage incident notification decisions."""

from sentinel.state import IncidentStateStore


class AlertManager:
    """Decide whether an incident should trigger a new notification."""

    def __init__(self, store: IncidentStateStore) -> None:
        self.store = store

    def evaluate(
        self,
        active_fingerprints: set[str],
    ) -> dict[str, list[str]]:
        """Return which incidents are new, ongoing, or recovered.

        Only new incidents should trigger a notification in this
        initial version. Ongoing incidents are tracked without
        generating another notification.
        """
        return self.store.update(active_fingerprints)
