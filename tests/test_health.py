def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "筑脉企服 Backend"
    assert payload["docs"] == "/docs"


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "筑脉企服 Backend"
    assert payload["environment"] == "test"
    assert payload["database"] == "ok"


def test_openapi_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "筑脉企服 Backend"
    assert "/api/health" in payload["paths"]
    assert "/api/opportunity-sources/{source_id}/analyze" in payload["paths"]
    assert "/api/intelligence-runs/{run_id}" in payload["paths"]
    assert "/api/me" in payload["paths"]
