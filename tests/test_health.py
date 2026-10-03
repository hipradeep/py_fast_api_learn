from fastapi.testclient import TestClient


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readiness_checks_database(self, client: TestClient) -> None:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        assert response.json()["database"] == "connected"


class TestOpenAPI:
    def test_openapi_schema_is_valid(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "py_fast_api_learn"
        assert "/api/v1/orders" in schema["paths"]

    def test_docs_endpoint(self, client: TestClient) -> None:
        assert client.get("/docs").status_code == 200