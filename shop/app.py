"""Shop REST API + static storefront.

Run:  uvicorn shop.app:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, pricing

MIN_QTY, MAX_QTY = 1, 20
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app):
    db.reset_db()
    yield


app = FastAPI(title="Shop API", lifespan=lifespan)


def error(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


# ---------- request bodies ----------

class AddItem(BaseModel):
    product_id: int
    qty: int = 1


class SetQty(BaseModel):
    qty: int


class ApplyCoupon(BaseModel):
    code: str


# ---------- helpers ----------

def check_qty(qty: int):
    if not MIN_QTY <= qty <= MAX_QTY:
        error(422, "QTY_RANGE", f"Quantity must be between {MIN_QTY} and {MAX_QTY}")


def get_open_cart(conn, cart_id: int):
    cart = conn.execute("SELECT * FROM carts WHERE id = ?", (cart_id,)).fetchone()
    if cart is None:
        error(404, "CART_NOT_FOUND", f"Cart {cart_id} does not exist")
    if cart["checked_out"]:
        error(409, "CART_CLOSED", "Cart has already been checked out")
    return cart


def cart_view(conn, cart_id: int):
    items = conn.execute(
        """SELECT p.id, p.name, p.price, p.emoji, ci.qty
           FROM cart_items ci JOIN products p ON p.id = ci.product_id
           WHERE ci.cart_id = ? ORDER BY p.id""",
        (cart_id,),
    ).fetchall()
    coupons = conn.execute(
        """SELECT c.code, c.kind, c.value FROM cart_coupons cc
           JOIN coupons c ON c.code = cc.code WHERE cc.cart_id = ?""",
        (cart_id,),
    ).fetchall()
    q = pricing.quote(
        [(i["price"], i["qty"]) for i in items],
        [(c["kind"], c["value"]) for c in coupons],
    )
    return {
        "id": cart_id,
        "items": [
            {"product_id": i["id"], "name": i["name"], "emoji": i["emoji"],
             "price": i["price"], "qty": i["qty"]}
            for i in items
        ],
        "coupons": [c["code"] for c in coupons],
        **{k: str(v) for k, v in q.items()},
    }


# ---------- endpoints ----------

@app.get("/api/health")
def health():
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    return {"status": "ok", "products": count}


@app.post("/api/reset")
def reset():
    """Reload seed data. Used to prepare a clean environment before test runs."""
    db.reset_db()
    return {"status": "reset"}


@app.get("/api/products")
def list_products():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/carts", status_code=201)
def create_cart():
    with db.connect() as conn:
        cart_id = conn.execute("INSERT INTO carts DEFAULT VALUES").lastrowid
        return cart_view(conn, cart_id)


@app.get("/api/carts/{cart_id}")
def get_cart(cart_id: int):
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM carts WHERE id = ?", (cart_id,)).fetchone() is None:
            error(404, "CART_NOT_FOUND", f"Cart {cart_id} does not exist")
        return cart_view(conn, cart_id)


@app.post("/api/carts/{cart_id}/items")
def add_item(cart_id: int, body: AddItem):
    check_qty(body.qty)
    with db.connect() as conn:
        get_open_cart(conn, cart_id)
        if conn.execute("SELECT 1 FROM products WHERE id = ?", (body.product_id,)).fetchone() is None:
            error(404, "PRODUCT_NOT_FOUND", f"Product {body.product_id} does not exist")
        existing = conn.execute(
            "SELECT qty FROM cart_items WHERE cart_id = ? AND product_id = ?",
            (cart_id, body.product_id),
        ).fetchone()
        new_qty = body.qty + (existing["qty"] if existing else 0)
        check_qty(new_qty)
        conn.execute(
            """INSERT INTO cart_items (cart_id, product_id, qty) VALUES (?, ?, ?)
               ON CONFLICT (cart_id, product_id) DO UPDATE SET qty = excluded.qty""",
            (cart_id, body.product_id, new_qty),
        )
        return cart_view(conn, cart_id)


@app.patch("/api/carts/{cart_id}/items/{product_id}")
def set_item_qty(cart_id: int, product_id: int, body: SetQty):
    check_qty(body.qty)
    with db.connect() as conn:
        get_open_cart(conn, cart_id)
        updated = conn.execute(
            "UPDATE cart_items SET qty = ? WHERE cart_id = ? AND product_id = ?",
            (body.qty, cart_id, product_id),
        ).rowcount
        if not updated:
            error(404, "ITEM_NOT_IN_CART", f"Product {product_id} is not in the cart")
        return cart_view(conn, cart_id)


@app.delete("/api/carts/{cart_id}/items/{product_id}")
def remove_item(cart_id: int, product_id: int):
    with db.connect() as conn:
        get_open_cart(conn, cart_id)
        conn.execute(
            "DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, product_id)
        )
        return cart_view(conn, cart_id)


@app.post("/api/carts/{cart_id}/coupons")
def apply_coupon(cart_id: int, body: ApplyCoupon):
    code = body.code.strip().upper()
    with db.connect() as conn:
        get_open_cart(conn, cart_id)
        if conn.execute("SELECT 1 FROM coupons WHERE code = ?", (code,)).fetchone() is None:
            error(404, "COUPON_NOT_FOUND", f"Coupon {code} does not exist")
        applied = conn.execute(
            "SELECT COUNT(*) FROM cart_coupons WHERE cart_id = ? AND code = ?", (cart_id, code)
        ).fetchone()[0]
        if applied >= 1:
            error(409, "COUPON_LIMIT", "Only one coupon can be used per order")
        conn.execute("INSERT INTO cart_coupons VALUES (?, ?)", (cart_id, code))
        return cart_view(conn, cart_id)


@app.delete("/api/carts/{cart_id}/coupons/{code}")
def remove_coupon(cart_id: int, code: str):
    with db.connect() as conn:
        get_open_cart(conn, cart_id)
        conn.execute(
            "DELETE FROM cart_coupons WHERE cart_id = ? AND code = ?", (cart_id, code.upper())
        )
        return cart_view(conn, cart_id)


@app.post("/api/carts/{cart_id}/checkout")
def checkout(cart_id: int):
    with db.connect() as conn:
        get_open_cart(conn, cart_id)
        view = cart_view(conn, cart_id)
        if not view["items"]:
            error(400, "EMPTY_CART", "Cart is empty")

        # Check every item first so a failed checkout never removes any stock.
        for item in view["items"]:
            stock = conn.execute(
                "SELECT stock FROM products WHERE id = ?", (item["product_id"],)
            ).fetchone()["stock"]
            if item["qty"] > stock:
                error(409, "OUT_OF_STOCK", f"Only {stock} left of {item['name']}")
        for item in view["items"]:
            conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (item["qty"], item["product_id"]),
            )

        order_id = conn.execute(
            "INSERT INTO orders (cart_id, total) VALUES (?, ?)",
            (cart_id, view["total"]),
        ).lastrowid
        conn.execute("UPDATE carts SET checked_out = 1 WHERE id = ?", (cart_id,))
    return {"order_id": order_id, "total": view["total"]}


# ---------- storefront ----------

@app.get("/")
def storefront():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
