from fastapi.testclient import TestClient

from app.main import create_app


def test_inspection_summary_and_bounded_candidates() -> None:
    client = TestClient(create_app())
    summary = client.get("/api/v1/inspection/summary")
    assert summary.status_code == 200
    assert summary.json()["selected_threshold"] == 39725
    response = client.get("/api/v1/inspection/candidates", params={"flag": "missing_candidate", "limit": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert len(payload["items"]) == 3
    assert all(item["flag"] == "missing_candidate" for item in payload["items"])
