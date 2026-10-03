from fastapi.testclient import TestClient


class TestUsers:
    def test_create_and_fetch_user(self, client: TestClient, clean_db) -> None:
        created = client.post(
            "/api/v1/users",
            json={"email": "alice@example.com", "full_name": "Alice"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["email"] == "alice@example.com"
        assert body["is_active"] is True

        fetched = client.get(f"/api/v1/users/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["full_name"] == "Alice"

    def test_duplicate_email_returns_409(self, client: TestClient, clean_db) -> None:
        payload = {"email": "dup@example.com", "full_name": "First"}
        assert client.post("/api/v1/users", json=payload).status_code == 201
        second = client.post("/api/v1/users", json=payload)
        assert second.status_code == 409
        assert second.json()["code"] == "conflict"

    def test_missing_user_returns_404(self, client: TestClient, clean_db) -> None:
        response = client.get("/api/v1/users/999999")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    def test_email_is_normalised_to_lowercase(self, client: TestClient, clean_db) -> None:
        created = client.post(
            "/api/v1/users", json={"email": "MiXeD@Example.COM", "full_name": "Mixed"}
        )
        assert created.json()["email"] == "mixed@example.com"

    def test_update_and_deactivate(self, client: TestClient, user: dict) -> None:
        updated = client.patch(f"/api/v1/users/{user['id']}", json={"full_name": "Renamed"})
        assert updated.status_code == 200
        assert updated.json()["full_name"] == "Renamed"

        deactivated = client.post(f"/api/v1/users/{user['id']}/deactivate")
        assert deactivated.json()["is_active"] is False

    def test_list_users_is_paginated(self, client: TestClient, clean_db) -> None:
        for index in range(3):
            client.post(
                "/api/v1/users",
                json={"email": f"page{index}@example.com", "full_name": f"User {index}"},
            )
        response = client.get("/api/v1/users", params={"page": 1, "page_size": 2})
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["pages"] == 2


class TestInventory:
    def test_create_product_normalises_sku(self, client: TestClient, clean_db) -> None:
        response = client.post(
            "/api/v1/inventory/products",
            json={
                "sku": "  abc-123 ",
                "name": "Widget",
                "unit_price": "9.99",
                "quantity_in_stock": 4,
                "reorder_level": 2,
            },
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "ABC-123"
        assert response.json()["quantity_in_stock"] == 4

    def test_duplicate_sku_returns_409(self, client: TestClient, clean_db) -> None:
        payload = {"sku": "DUP-1", "name": "First", "unit_price": "1.00"}
        assert client.post("/api/v1/inventory/products", json=payload).status_code == 201
        assert client.post("/api/v1/inventory/products", json=payload).status_code == 409

    def test_restock_increases_quantity(self, client: TestClient, products) -> None:
        product_id = products[0]["id"]
        response = client.post(
            f"/api/v1/inventory/products/{product_id}/restock",
            params={"quantity": 5, "reason": "New shipment"},
        )
        assert response.status_code == 200
        assert response.json()["quantity_in_stock"] == 15

    def test_restock_rejects_non_positive_quantity(self, client: TestClient, products) -> None:
        response = client.post(
            f"/api/v1/inventory/products/{products[0]['id']}/restock",
            params={"quantity": 0},
        )
        assert response.status_code == 422

    def test_manual_adjustment_can_write_off_stock(
        self, client: TestClient, products
    ) -> None:
        response = client.post(
            f"/api/v1/inventory/products/{products[0]['id']}/stock",
            json={"quantity_delta": -3, "reason": "Damaged goods"},
        )
        assert response.status_code == 200
        assert response.json()["quantity_in_stock"] == 7

    def test_cannot_write_off_more_than_available(
        self, client: TestClient, products
    ) -> None:
        response = client.post(
            f"/api/v1/inventory/products/{products[0]['id']}/stock",
            json={"quantity_delta": -999},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "business_rule_violation"

    def test_low_stock_filter(self, client: TestClient, products) -> None:
        # product A has 10 in stock / reorder 3  -> healthy
        # product B has 2 in stock / reorder 5   -> low
        # product C has 0 in stock / reorder 2   -> low
        response = client.get("/api/v1/inventory/products", params={"low_stock": True})
        assert response.status_code == 200
        skus = {item["sku"] for item in response.json()["items"]}
        assert len(skus) == 2

    def test_low_stock_endpoint(self, client: TestClient, products) -> None:
        response = client.get("/api/v1/inventory/low-stock")
        assert response.status_code == 200
        assert all(item["is_low_stock"] for item in response.json())

    def test_stock_movements_are_recorded(self, client: TestClient, products) -> None:
        product_id = products[0]["id"]
        client.post(
            f"/api/v1/inventory/products/{product_id}/restock", params={"quantity": 4}
        )
        response = client.get(f"/api/v1/inventory/products/{product_id}/movements")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["items"][0]["movement_type"] == "restock"
        assert body["items"][0]["quantity_change"] == 4

    def test_inventory_summary(self, client: TestClient, products) -> None:
        response = client.get("/api/v1/inventory/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total_products"] == 3
        assert body["out_of_stock_count"] == 1
        assert body["low_stock_count"] == 2