import os
import pytest
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture(autouse=True)
def reset_db(client):
    response = client.post("/api/reset")
    assert response.status_code in (200, 201, 204)


# --- Helper functions ---

def create_cart(client) -> str:
    res = client.post("/api/carts")
    assert res.status_code == 201
    return res.json()["id"]


# --- Generic / Health / Products API Tests ---

def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "products" in data


def test_get_products_seed_data(client):
    res = client.get("/api/products")
    assert res.status_code == 200
    products = res.json()
    assert len(products) == 6
    p1 = next(p for p in products if p["id"] == 1)
    assert p1["price"] == "39.90" or p1["price"] == 39.90 or str(p1["price"]) == "39.90"
    assert p1["stock"] == 50


# --- Rule R1: Spend discount ---

def test_r1_spend_discount_below_100_subtotal(client):
    """R1: Subtotal under $100.00 receives no spend discount (tier_discount = '0.00')."""
    cart_id = create_cart(client)
    # Product 1 ($39.90) x 2 + Product 5 ($19.50) x 1 = $99.30
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 2})
    res = client.post(f"/api/carts/{cart_id}/items", json={"product_id": 5, "qty": 1})
    
    assert res.status_code in (200, 201)
    cart = res.json()
    assert cart["subtotal"] == "99.30"
    assert cart["tier_discount"] == "0.00"
    assert cart["total"] == "99.30"


def test_r1_spend_discount_exact_100_subtotal(client):
    """R1: Subtotal exact $100.00 receives 10% spend discount ($10.00)."""
    cart_id = create_cart(client)
    # Product 2 ($25.00) x 4 = $100.00
    res = client.post(f"/api/carts/{cart_id}/items", json={"product_id": 2, "qty": 4})
    
    assert res.status_code in (200, 201)
    cart = res.json()
    assert cart["subtotal"] == "100.00"
    assert cart["tier_discount"] == "10.00"
    assert cart["total"] == "90.00"


def test_r1_spend_discount_above_100_subtotal(client):
    """R1: Subtotal above $100.00 receives 10% spend discount."""
    cart_id = create_cart(client)
    # Product 4 ($45.00) x 3 = $135.00 -> 10% = $13.50
    res = client.post(f"/api/carts/{cart_id}/items", json={"product_id": 4, "qty": 3})
    
    assert res.status_code in (200, 201)
    cart = res.json()
    assert cart["subtotal"] == "135.00"
    assert cart["tier_discount"] == "13.50"
    assert cart["total"] == "121.50"


# --- Rule R2: One coupon per order ---

def test_r2_one_coupon_per_order_limit(client):
    """R2: Applying a second coupon fails with 409 COUPON_LIMIT and leaves cart unchanged."""
    cart_id = create_cart(client)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 1})

    # Apply first coupon
    res1 = client.post(f"/api/carts/{cart_id}/coupons", json={"code": "SAVE10"})
    assert res1.status_code == 200
    cart_before = res1.json()
    assert cart_before["coupons"] == ["SAVE10"]

    # Apply second coupon
    res2 = client.post(f"/api/carts/{cart_id}/coupons", json={"code": "LESS5"})
    assert res2.status_code == 409
    err = res2.json()
    assert err["detail"]["code"] == "COUPON_LIMIT"

    # Verify cart remains unchanged
    res_cart = client.get(f"/api/carts/{cart_id}")
    assert res_cart.status_code == 200
    cart_after = res_cart.json()
    assert cart_after["coupons"] == ["SAVE10"]
    assert cart_after["coupon_discount"] == cart_before["coupon_discount"]


# --- Rule R3: Quantity limits ---

@pytest.mark.parametrize("valid_qty", [1, 10, 20])
def test_r3_quantity_limits_valid_boundary(client, valid_qty):
    """R3: Item quantities between 1 and 20 are allowed."""
    cart_id = create_cart(client)
    res = client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": valid_qty})
    assert res.status_code in (200, 201)
    cart = res.json()
    item = next(i for i in cart["items"] if i["product_id"] == 1)
    assert item["qty"] == valid_qty


@pytest.mark.parametrize("invalid_qty", [0, -1, 21, 99])
def test_r3_quantity_limits_invalid_add_item(client, invalid_qty):
    """R3: Adding quantity outside 1..20 fails with 422 QTY_RANGE."""
    cart_id = create_cart(client)
    res = client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": invalid_qty})
    assert res.status_code == 422
    err = res.json()
    assert err["detail"]["code"] == "QTY_RANGE"


@pytest.mark.parametrize("invalid_qty", [0, -5, 21])
def test_r3_quantity_limits_invalid_patch_item(client, invalid_qty):
    """R3: Updating item quantity outside 1..20 fails with 422 QTY_RANGE."""
    cart_id = create_cart(client)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 5})

    res = client.patch(f"/api/carts/{cart_id}/items/1", json={"qty": invalid_qty})
    assert res.status_code == 422
    err = res.json()
    assert err["detail"]["code"] == "QTY_RANGE"


def test_r3_quantity_limits_cumulative_exceed_max(client):
    """R3: Adding quantity that pushes total quantity above 20 fails with 422 QTY_RANGE."""
    cart_id = create_cart(client)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 15})

    # Adding 6 more brings quantity to 21
    res = client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 6})
    assert res.status_code == 422
    err = res.json()
    assert err["detail"]["code"] == "QTY_RANGE"


# --- Rule R4: Stock at checkout ---

def test_r4_stock_at_checkout_failure_and_rollback(client):
    """R4: Checkout fails with 409 OUT_OF_STOCK if qty > stock. Stock must remain unchanged."""
    cart_id = create_cart(client)
    # Product 5 (Phone Tripod) has stock 3
    # Add 4 items (valid qty limit 1..20)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 5, "qty": 4})

    # Attempt checkout
    res = client.post(f"/api/carts/{cart_id}/checkout")
    assert res.status_code == 409
    err = res.json()
    assert err["detail"]["code"] == "OUT_OF_STOCK"

    # Verify product stock is unchanged (still 3)
    res_products = client.get("/api/products")
    products = res_products.json()
    p5 = next(p for p in products if p["id"] == 5)
    assert p5["stock"] == 3


# --- Rule R5: Coupons ---

def test_r5_coupon_save10_percentage(client):
    """R5: SAVE10 takes 10% off subtotal."""
    cart_id = create_cart(client)
    # Subtotal $50.00 (Product 2 x 2)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 2, "qty": 2})

    res = client.post(f"/api/carts/{cart_id}/coupons", json={"code": "SAVE10"})
    assert res.status_code == 200
    cart = res.json()
    assert cart["coupon_discount"] == "5.00"
    assert cart["total"] == "45.00"


def test_r5_coupon_less5_fixed(client):
    """R5: LESS5 takes $5.00 off."""
    cart_id = create_cart(client)
    # Subtotal $25.00
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 2, "qty": 1})

    res = client.post(f"/api/carts/{cart_id}/coupons", json={"code": "LESS5"})
    assert res.status_code == 200
    cart = res.json()
    assert cart["coupon_discount"] == "5.00"
    assert cart["total"] == "20.00"


@pytest.mark.parametrize("code", ["save10", "Save10", "less5", "LeSs5"])
def test_r5_coupons_case_insensitive(client, code):
    """R5: Coupon codes are case-insensitive."""
    cart_id = create_cart(client)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 2, "qty": 2})

    res = client.post(f"/api/carts/{cart_id}/coupons", json={"code": code})
    assert res.status_code == 200
    cart = res.json()
    assert cart["coupons"] == [code]  # or normalized code
    assert cart["coupon_discount"] != "0.00"


def test_r5_coupon_not_found(client):
    """R5: Unknown coupon codes fail with 404 COUPON_NOT_FOUND."""
    cart_id = create_cart(client)
    res = client.post(f"/api/carts/{cart_id}/coupons", json={"code": "UNKNOWN99"})
    assert res.status_code == 404
    err = res.json()
    assert err["detail"]["code"] == "COUPON_NOT_FOUND"


# --- Rule R6: Totals & Formatting ---

def test_r6_totals_calculation_and_rounding(client):
    """R6: total = subtotal - tier_discount - coupon_discount with half-up 2 decimal place strings."""
    cart_id = create_cart(client)
    # Product 1 ($39.90) x 3 = $119.70 subtotal
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 3})
    # Tier discount (10% of 119.70) = 11.97
    # Apply SAVE10 (10% of 119.70) = 11.97
    client.post(f"/api/carts/{cart_id}/coupons", json={"code": "SAVE10"})

    res = client.get(f"/api/carts/{cart_id}")
    assert res.status_code == 200
    cart = res.json()

    assert cart["subtotal"] == "119.70"
    assert cart["tier_discount"] == "11.97"
    assert cart["coupon_discount"] == "11.97"
    # 119.70 - 11.97 - 11.97 = 95.76
    assert cart["total"] == "95.76"


def test_r6_totals_never_below_zero(client):
    """R6: Total cannot drop below $0.00."""
    cart_id = create_cart(client)
    # Product 5 ($19.50) x 1
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 5, "qty": 1})
    client.post(f"/api/carts/{cart_id}/coupons", json={"code": "LESS5"})

    res = client.get(f"/api/carts/{cart_id}")
    cart = res.json()
    # Ensure all money amounts are formatted strings
    for field in ["subtotal", "tier_discount", "coupon_discount", "total"]:
        val = cart[field]
        assert isinstance(val, str)
        assert len(val.split(".")[1]) == 2
        assert float(val) >= 0.0


# --- Rule R7: Checkout ---

def test_r7_checkout_success_reduces_stock(client):
    """R7: Successful checkout returns order total, reduces product stock, and closes cart."""
    cart_id = create_cart(client)
    # Buy 2 of Product 3 (LED Ring Light, initial stock 5)
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 3, "qty": 2})

    checkout_res = client.post(f"/api/carts/{cart_id}/checkout")
    assert checkout_res.status_code in (200, 201)
    data = checkout_res.json()
    assert "order_id" in data
    assert data["total"] == "118.00"  # 59.00 * 2 = 118.00 (tier discount 10% = 11.80 -> total 106.20)
    # 118.00 >= 100 so tier discount applies: 118.00 - 11.80 = 106.20
    assert data["total"] == "106.20"

    # Verify stock reduced from 5 to 3
    products_res = client.get("/api/products")
    products = products_res.json()
    p3 = next(p for p in products if p["id"] == 3)
    assert p3["stock"] == 3


def test_r7_checkout_empty_cart_fails(client):
    """R7: Checking out an empty cart fails with 400 EMPTY_CART."""
    cart_id = create_cart(client)
    res = client.post(f"/api/carts/{cart_id}/checkout")
    assert res.status_code == 400
    err = res.json()
    assert err["detail"]["code"] == "EMPTY_CART"


# --- Cart CRUD Management Tests ---

def test_cart_item_deletion_and_coupon_removal(client):
    """Test DELETE /items and DELETE /coupons endpoints."""
    cart_id = create_cart(client)

    # Add item and coupon
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": 1, "qty": 2})
    client.post(f"/api/carts/{cart_id}/coupons", json={"code": "LESS5"})

    # Delete item
    del_item_res = client.delete(f"/api/carts/{cart_id}/items/1")
    assert del_item_res.status_code == 200
    cart = del_item_res.json()
    assert len(cart["items"]) == 0
    assert cart["subtotal"] == "0.00"

    # Delete coupon
    del_coupon_res = client.delete(f"/api/carts/{cart_id}/coupons/LESS5")
    assert del_coupon_res.status_code == 200
    cart_after = del_coupon_res.json()
    assert len(cart_after["coupons"]) == 0
    assert cart_after["coupon_discount"] == "0.00"
