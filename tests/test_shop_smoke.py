"""Smoke tests: the shop starts and its main endpoints respond.

Business-rule tests are deliberately left to the AI test platform.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from shop import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    from shop.app import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "products": 6}


def test_storefront_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert 'data-testid="product-grid"' in res.text


def test_cart_flow(client):
    cart = client.post("/api/carts").json()
    cart = client.post(f"/api/carts/{cart['id']}/items", json={"product_id": 1, "qty": 1}).json()
    assert [i["product_id"] for i in cart["items"]] == [1]

    order = client.post(f"/api/carts/{cart['id']}/checkout").json()
    assert order["total"] == cart["total"]


def test_unknown_product(client):
    cart = client.post("/api/carts").json()
    res = client.post(f"/api/carts/{cart['id']}/items", json={"product_id": 999})
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "PRODUCT_NOT_FOUND"
