"""Tests for duplicate-alert suppression."""

from src.sentinel.alert_manager import AlertManager
from src.sentinel.state import IncidentStateStore


def test_new_incident_is_eligible_for_alert(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    manager = AlertManager(store)

    result = manager.evaluate({"TIMEOUT:timeouterror"})

    assert result["new"] == ["TIMEOUT:timeouterror"]
    assert result["ongoing"] == []


def test_repeated_incident_does_not_trigger_another_new_alert(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    manager = AlertManager(store)
    fingerprint = "TIMEOUT:timeouterror"

    manager.evaluate({fingerprint})
    result = manager.evaluate({fingerprint})

    assert result["new"] == []
    assert result["ongoing"] == [fingerprint]


def test_recovered_incident_is_reported(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    manager = AlertManager(store)
    fingerprint = "TIMEOUT:timeouterror"

    manager.evaluate({fingerprint})
    manager.evaluate(set())
    result = manager.evaluate(set())

    assert result["recovered"] == [fingerprint]
