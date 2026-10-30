"""SQLite storage and seed data for the shop."""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("SHOP_DB", "shop.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    price       TEXT NOT NULL,          -- decimal string, e.g. "25.00"
    stock       INTEGER NOT NULL,
    emoji       TEXT NOT NULL,
    creator     TEXT,                   -- creator who features the product
    flash_sale  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupons (
    code   TEXT PRIMARY KEY,
    kind   TEXT NOT NULL CHECK (kind IN ('percent', 'fixed')),
    value  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    creator     TEXT,
    checked_out INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cart_items (
    cart_id    INTEGER NOT NULL REFERENCES carts(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL,
    PRIMARY KEY (cart_id, product_id)
);
CREATE TABLE IF NOT EXISTS cart_coupons (
    cart_id INTEGER NOT NULL REFERENCES carts(id),
    code    TEXT NOT NULL REFERENCES coupons(code),
    PRIMARY KEY (cart_id, code)
);
CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cart_id    INTEGER NOT NULL REFERENCES carts(id),
    total      TEXT NOT NULL,
    creator    TEXT,
    commission TEXT NOT NULL
);
"""

PRODUCTS = [
    (1, "Wireless Earbuds", "39.90", 50, "🎧", "techwithjo", 0),
    (2, "Glow Serum", "25.00", 100, "✨", "skinbyrina", 0),
    (3, "LED Ring Light", "59.00", 5, "💡", "creatorkit", 1),
    (4, "Oversized Hoodie", "45.00", 30, "🧥", None, 0),
    (5, "Phone Tripod", "19.50", 3, "📱", "creatorkit", 1),
    (6, "Matcha Starter Kit", "32.00", 40, "🍵", "dailyleaf", 0),
]

COUPONS = [
    ("SAVE10", "percent", "10"),
    ("LESS5", "fixed", "5.00"),
]


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_db():
    """Drop everything and reload seed data, giving tests a known starting state."""
    with connect() as conn:
        for table in ("orders", "cart_coupons", "cart_items", "carts", "coupons", "products"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", PRODUCTS)
        conn.executemany("INSERT INTO coupons VALUES (?, ?, ?)", COUPONS)
