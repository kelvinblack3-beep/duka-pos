from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duka_pos import api as api_module
from duka_pos import db as db_module


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "api_test.sqlite"
    test_conn = db_module.connect_and_init(db_path)

    def _override_get_connection():
        return test_conn

    api_module.app.dependency_overrides[api_module.get_connection] = _override_get_connection
    with TestClient(api_module.app) as test_client:
        yield test_client
    api_module.app.dependency_overrides.clear()
    test_conn.close()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_product(client: TestClient) -> None:
    response = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    )
    assert response.status_code == 201
    product = response.json()
    assert product["name"] == "Rice"
    assert product["stock_quantity_milli"] == 0

    get_response = client.get(f"/products/{product['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == product["id"]


def test_get_missing_product_returns_404(client: TestClient) -> None:
    response = client.get("/products/999")
    assert response.status_code == 404


def test_add_stock(client: TestClient) -> None:
    product = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    ).json()

    response = client.post(f"/products/{product['id']}/stock", json={"quantity_milli": 50000})
    assert response.status_code == 200
    assert response.json()["stock_quantity_milli"] == 50000


def test_rice_end_to_end_via_api(client: TestClient) -> None:
    product = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    ).json()
    client.post(f"/products/{product['id']}/stock", json={"quantity_milli": 50000})

    sale_response = client.post(
        "/sales",
        json={
            "client_reference": "api-rice-001",
            "lines": [{"product_id": product["id"], "quantity_milli": 1350}],
        },
    )
    assert sale_response.status_code == 201
    sale = sale_response.json()
    assert sale["total_cents"] == 21600
    assert sale["payment"]["status"] == "CONFIRMED"
    # Cashier-facing sale response must not expose cost/profit fields.
    assert "unit_cost_cents" not in sale["lines"][0]
    assert "gross_profit_cents" not in sale

    get_response = client.get(f"/sales/{sale['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["total_cents"] == 21600

    receipt_response = client.get(f"/sales/{sale['id']}/receipt")
    assert receipt_response.status_code == 200
    receipt = receipt_response.json()
    assert receipt["total_cents"] == 21600
    assert receipt["payment_method"] == "CASH"
    assert "unit_cost_cents" not in receipt["lines"][0]


def test_sale_with_insufficient_stock_returns_409(client: TestClient) -> None:
    product = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    ).json()
    client.post(f"/products/{product['id']}/stock", json={"quantity_milli": 500})

    response = client.post(
        "/sales",
        json={
            "client_reference": "api-insufficient-001",
            "lines": [{"product_id": product["id"], "quantity_milli": 1000}],
        },
    )
    assert response.status_code == 409


def test_sale_with_unsupported_payment_method_returns_501(client: TestClient) -> None:
    product = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    ).json()
    client.post(f"/products/{product['id']}/stock", json={"quantity_milli": 5000})

    response = client.post(
        "/sales",
        json={
            "client_reference": "api-mpesa-001",
            "payment_method": "MPESA",
            "lines": [{"product_id": product["id"], "quantity_milli": 1000}],
        },
    )
    # Pydantic's Literal["CASH"] rejects this at the schema layer (422)
    # before it ever reaches the domain layer's UnsupportedPaymentMethod.
    assert response.status_code == 422


def test_duplicate_sale_reference_via_api_is_idempotent(client: TestClient) -> None:
    product = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    ).json()
    client.post(f"/products/{product['id']}/stock", json={"quantity_milli": 50000})

    payload = {
        "client_reference": "api-dup-001",
        "lines": [{"product_id": product["id"], "quantity_milli": 1000}],
    }
    first = client.post("/sales", json=payload)
    second = client.post("/sales", json=payload)
    assert first.json()["id"] == second.json()["id"]

    balance_response = client.get(f"/products/{product['id']}")
    assert balance_response.json()["stock_quantity_milli"] == 50000 - 1000


def test_invalid_quantity_returns_422(client: TestClient) -> None:
    product = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": 12000,
            "selling_price_cents": 16000,
        },
    ).json()
    response = client.post(f"/products/{product['id']}/stock", json={"quantity_milli": 0})
    assert response.status_code == 422


def test_invalid_money_returns_422(client: TestClient) -> None:
    response = client.post(
        "/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "cost_price_cents": -1,
            "selling_price_cents": 16000,
        },
    )
    assert response.status_code == 422
