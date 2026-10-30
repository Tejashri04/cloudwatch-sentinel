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


def test_one_missing_run_does_not_mark_incident_recovered(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    fingerprint = "TIMEOUT:timeouterror"

    store.update({fingerprint})
    result = store.update(set())

    assert result["recovered"] == []

    saved = store.load()
    assert saved[fingerprint]["status"] == "OPEN"
    assert saved[fingerprint]["missing_runs"] == 1


def test_incident_is_recovered_after_two_missing_runs(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    fingerprint = "TIMEOUT:timeouterror"

    store.update({fingerprint})
    store.update(set())
    result = store.update(set())

    assert result["recovered"] == [fingerprint]
    assert store.load()[fingerprint]["status"] == "RESOLVED"


def test_reappearing_resolved_incident_is_new(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))
    fingerprint = "TIMEOUT:timeouterror"

    store.update({fingerprint})
    store.update(set())
    store.update(set())

    result = store.update({fingerprint})

    assert result["new"] == [fingerprint]


def test_empty_store_has_no_incidents(tmp_path):
    store = IncidentStateStore(str(tmp_path / "incidents.json"))

    assert store.load() == {}
