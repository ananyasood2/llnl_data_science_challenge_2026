from fastapi.testclient import TestClient

from app.main import create_app


def test_binary_metrics() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/metrics/classification",
        json={
            "y_true": ["missing", "missing", "clear", "clear", "missing"],
            "y_pred": ["missing", "clear", "clear", "clear", "missing"],
            "average": "binary",
            "positive_label": "missing",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["accuracy"] == 0.8
    assert payload["precision"] == 1.0
    assert round(payload["recall"], 4) == round(2 / 3, 4)
    assert payload["support"] == 5
    assert set(payload["per_class"].keys()) == {"missing", "clear"}


def test_macro_and_weighted_average() -> None:
    client = TestClient(create_app())
    body = {
        "y_true": ["a", "b", "c", "a", "b", "c"],
        "y_pred": ["a", "b", "b", "a", "a", "c"],
    }
    macro = client.post("/api/v1/metrics/classification", json={**body, "average": "macro"}).json()
    weighted = client.post("/api/v1/metrics/classification", json={**body, "average": "weighted"}).json()
    assert macro["average"] == "macro"
    assert weighted["average"] == "weighted"
    assert 0 <= macro["f1"] <= 1
    assert 0 <= weighted["f1"] <= 1


def test_mismatched_lengths_rejected() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/metrics/classification",
        json={"y_true": ["a", "b"], "y_pred": ["a"]},
    )
    assert response.status_code == 422
