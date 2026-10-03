import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.core.database import engine
from app.main import app
from app.models import Order, OrderItem, Product, StockMovement, User


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def clean_db():
    """Guarantees a clean slate per test and rolls everything back afterwards."""
    with Session(engine) as session:
        for model in (StockMovement, OrderItem, Order, Product, User):
            session.exec(delete(model))
        session.commit()

    yield

    with Session(engine) as session:
        for model in (StockMovement, OrderItem, Order, Product, User):
            session.exec(delete(model))
        session.commit()


@pytest.fixture
def user(client: TestClient, clean_db) -> dict:
    suffix = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/users",
        json={
            "email": f"user_{suffix}@example.com",
            "full_name": "Test User",
            "phone": "+15550000",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def products(client: TestClient, clean_db) -> list[dict]:
    suffix = uuid.uuid4().hex[:6].upper()
    created = []
    for index, (sku, stock, reorder) in enumerate(
        [(f"SKU-A-{suffix}", 10, 3), (f"SKU-B-{suffix}", 2, 5), (f"SKU-C-{suffix}", 0, 2)]
    ):
        response = client.post(
            "/api/v1/inventory/products",
            json={
                "sku": sku,
                "name": f"Product {index}",
                "unit_price": "10.50",
                "quantity_in_stock": stock,
                "reorder_level": reorder,
            },
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    return created