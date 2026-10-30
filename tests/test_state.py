"""Tests for incident state tracking."""

from src.sentinel.state import IncidentStateStore


def test_first_occurrence_is_new(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))

    result = store.update({"TIMEOUT:timeouterror"})

    assert result["new"] == ["TIMEOUT:timeouterror"]
    assert result["ongoing"] == []
    assert result["recovered"] == []


def test_repeated_occurrence_is_ongoing(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    fingerprint = "TIMEOUT:timeouterror"

    store.update({fingerprint})
    result = store.update({fingerprint})

    assert result["new"] == []
    assert result["ongoing"] == [fingerprint]
    assert result["recovered"] == []


def test_missing_incident_is_marked_recovered(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    fingerprint = "TIMEOUT:timeouterror"

    store.update({fingerprint})
    result = store.update(set())

    assert result["recovered"] == [fingerprint]


def test_reappearing_resolved_incident_is_new(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    fingerprint = "TIMEOUT:timeouterror"

    store.update({fingerprint})
    store.update(set())
    result = store.update({fingerprint})

    assert result["new"] == [fingerprint]


def test_empty_store_has_no_incidents(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))

    assert store.load() == {}
