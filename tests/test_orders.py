from fastapi.testclient import TestClient

from app.models.enums import OrderStatus


def place_order(client: TestClient, user_id: int, products: list[dict], **extra) -> dict:
    payload = {
        "user_id": user_id,
        "items": [
            {"product_id": products[0]["id"], "quantity": 2},
            {"product_id": products[1]["id"], "quantity": 1},
        ],
        **extra,
    }
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestOrderCreation:
    def test_order_decrements_stock_and_computes_totals(
        self, client: TestClient, user, products
    ) -> None:
        order = place_order(client, user["id"], products, tax_rate="0.10")

        assert order["status"] == OrderStatus.PENDING.value
        assert order["subtotal"] == "31.50"  # 2 x 10.50 + 1 x 10.50
        assert order["tax_amount"] == "3.15"
        assert order["total_amount"] == "34.65"
        assert order["reference"].startswith("ORD-")
        assert len(order["items"]) == 2

        after = client.get(f"/api/v1/inventory/products/{products[0]['id']}").json()
        assert after["quantity_in_stock"] == 8

    def test_order_for_unknown_user_returns_404(
        self, client: TestClient, products
    ) -> None:
        response = client.post(
            "/api/v1/orders",
            json={
                "user_id": 999999,
                "items": [{"product_id": products[0]["id"], "quantity": 1}],
            },
        )
        assert response.status_code == 404

    def test_overselling_is_rejected_and_stock_untouched(
        self, client: TestClient, user, products
    ) -> None:
        # product B only has 2 units
        response = client.post(
            "/api/v1/orders",
            json={
                "user_id": user["id"],
                "items": [{"product_id": products[1]["id"], "quantity": 5}],
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "business_rule_violation"

        # the failed order must not have touched product A either
        assert client.get(f"/api/v1/inventory/products/{products[0]['id']}").json()[
            "quantity_in_stock"
        ] == 10

    def test_out_of_stock_product_is_rejected(
        self, client: TestClient, user, products
    ) -> None:
        response = client.post(
            "/api/v1/orders",
            json={
                "user_id": user["id"],
                "items": [{"product_id": products[2]["id"], "quantity": 1}],
            },
        )
        assert response.status_code == 400

    def test_duplicate_product_lines_are_rejected(
        self, client: TestClient, user, products
    ) -> None:
        response = client.post(
            "/api/v1/orders",
            json={
                "user_id": user["id"],
                "items": [
                    {"product_id": products[0]["id"], "quantity": 1},
                    {"product_id": products[0]["id"], "quantity": 2},
                ],
            },
        )
        assert response.status_code == 422

    def test_empty_order_is_rejected(self, client: TestClient, user) -> None:
        response = client.post(
            "/api/v1/orders", json={"user_id": user["id"], "items": []}
        )
        assert response.status_code == 422

    def test_inactive_user_cannot_order(
        self, client: TestClient, user, products
    ) -> None:
        client.post(f"/api/v1/users/{user['id']}/deactivate")
        response = client.post(
            "/api/v1/orders",
            json={
                "user_id": user["id"],
                "items": [{"product_id": products[0]["id"], "quantity": 1}],
            },
        )
        assert response.status_code == 400


class TestOrderStatus:
    def test_happy_path_transitions(self, client: TestClient, user, products) -> None:
        order = place_order(client, user["id"], products)

        for target in ("confirmed", "shipped", "delivered"):
            response = client.patch(
                f"/api/v1/orders/{order['id']}/status", json={"status": target}
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == target

    def test_illegal_transition_is_rejected(
        self, client: TestClient, user, products
    ) -> None:
        order = place_order(client, user["id"], products)
        response = client.patch(
            f"/api/v1/orders/{order['id']}/status", json={"status": "delivered"}
        )
        assert response.status_code == 400
        assert response.json()["code"] == "business_rule_violation"

    def test_transition_to_same_status_conflicts(
        self, client: TestClient, user, products
    ) -> None:
        order = place_order(client, user["id"], products)
        response = client.patch(
            f"/api/v1/orders/{order['id']}/status", json={"status": "pending"}
        )
        assert response.status_code == 409

    def test_cancel_restores_stock(self, client: TestClient, user, products) -> None:
        order = place_order(client, user["id"], products)
        assert client.get(f"/api/v1/inventory/products/{products[0]['id']}").json()[
            "quantity_in_stock"
        ] == 8

        cancelled = client.post(
            f"/api/v1/orders/{order['id']}/cancel", params={"reason": "Customer changed mind"}
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancelled_at"] is not None

        restored = client.get(f"/api/v1/inventory/products/{products[0]['id']}").json()
        assert restored["quantity_in_stock"] == 10

    def test_cancelled_order_is_terminal(self, client: TestClient, user, products) -> None:
        order = place_order(client, user["id"], products)
        client.post(f"/api/v1/orders/{order['id']}/cancel")

        response = client.patch(
            f"/api/v1/orders/{order['id']}/status", json={"status": "confirmed"}
        )
        assert response.status_code == 400

    def test_cancel_twice_conflicts(self, client: TestClient, user, products) -> None:
        order = place_order(client, user["id"], products)
        client.post(f"/api/v1/orders/{order['id']}/cancel")
        second = client.post(f"/api/v1/orders/{order['id']}/cancel")
        assert second.status_code == 409

    def test_cancellation_writes_stock_movements(
        self, client: TestClient, user, products
    ) -> None:
        order = place_order(client, user["id"], products)
        client.post(f"/api/v1/orders/{order['id']}/cancel")

        movements = client.get(
            f"/api/v1/inventory/products/{products[0]['id']}/movements"
        ).json()
        types = [m["movement_type"] for m in movements["items"]]
        assert "order_cancellation" in types
        assert "sale" in types


class TestOrderQueries:
    def test_filter_orders_by_status_and_user(
        self, client: TestClient, user, products
    ) -> None:
        place_order(client, user["id"], products)
        second = place_order(client, user["id"], products)
        client.patch(f"/api/v1/orders/{second['id']}/status", json={"status": "confirmed"})

        pending = client.get("/api/v1/orders", params={"status": "pending"}).json()
        assert pending["total"] == 1

        by_user = client.get("/api/v1/orders", params={"user_id": user["id"]}).json()
        assert by_user["total"] == 2

    def test_missing_order_returns_404(self, client: TestClient, clean_db) -> None:
        assert client.get("/api/v1/orders/999999").status_code == 404

    def test_delivered_order_cannot_be_deleted_away_from(
        self, client: TestClient, user, products
    ) -> None:
        order = place_order(client, user["id"], products)
        for target in ("confirmed", "shipped", "delivered"):
            client.patch(f"/api/v1/orders/{order['id']}/status", json={"status": target})

        response = client.delete(f"/api/v1/users/{user['id']}")
        assert response.status_code == 409