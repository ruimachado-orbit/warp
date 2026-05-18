import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "incident_cluster_eval_cases.json"


def test_incident_cluster_fixture_has_expected_shape():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "warp.incident_cluster_eval.v1"
    assert len(payload["tickets"]) == 30
    assert len(payload["expected_clusters"]) == 15

    ticket_ids = [ticket["ticket_id"] for ticket in payload["tickets"]]
    assert len(ticket_ids) == len(set(ticket_ids))

    incident_clusters = [
        cluster for cluster in payload["expected_clusters"] if cluster["kind"] == "incident"
    ]
    singleton_clusters = [
        cluster for cluster in payload["expected_clusters"] if cluster["kind"] == "singleton"
    ]

    assert len(incident_clusters) == 5
    assert not all(len(c["ticket_ids"]) == len(incident_clusters[0]["ticket_ids"]) for c in incident_clusters)
    assert len(singleton_clusters) == 10
    assert all(len(cluster["ticket_ids"]) == 1 for cluster in singleton_clusters)

    known_ticket_ids = set(ticket_ids)
    cluster_ticket_ids = {
        ticket_id for cluster in payload["expected_clusters"] for ticket_id in cluster["ticket_ids"]
    }
    assert cluster_ticket_ids == known_ticket_ids

    cluster_ids = {cluster["incident_id"] for cluster in payload["expected_clusters"]}
    assert {ticket["expected_incident_id"] for ticket in payload["tickets"]} == cluster_ids


def test_incident_cluster_fixture_has_pairwise_eval_notes():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    notes = payload["evaluation_notes"]
    assert "pairwise" in notes["primary_metric"]
    assert notes["singleton_policy"].startswith("singleton tickets should remain alone")
