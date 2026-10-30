# Shop requirements

Input for the AI test platform. Each rule has an ID that generated tests must cite.

## Business rules

- **R1 Spend discount.** Orders with a subtotal of $100.00 or more get 10% off the subtotal. Orders below $100.00 get no spend discount.
- **R2 One coupon per order.** At most one coupon can be applied to a cart. Applying a second coupon fails with `409 COUPON_LIMIT` and the cart is unchanged.
- **R3 Quantity limits.** The quantity of each item in a cart must be between 1 and 20. Anything outside that range fails with `422 QTY_RANGE`.
- **R4 Stock at checkout.** Checkout fails with `409 OUT_OF_STOCK` if any item's quantity exceeds the available stock. A failed checkout must not change the stock of any product.
- **R5 Coupons.** `SAVE10` takes 10% off the subtotal. `LESS5` takes $5.00 off. Coupon codes are case-insensitive. Unknown codes fail with `404 COUPON_NOT_FOUND`.
- **R6 Totals.** `total = subtotal - tier_discount - coupon_discount`, never below $0.00. All amounts are strings with 2 decimal places, rounded half-up.
- **R7 Checkout.** A successful checkout returns the order total, reduces each product's stock by the quantity bought, and closes the cart. Checking out an empty cart fails with `400 EMPTY_CART`.

## Seed data

Every app start (and `POST /api/reset`) restores this data.

| id | product | price | stock |
|---|---|---|---|
| 1 | Wireless Earbuds | 39.90 | 50 |
| 2 | Glow Serum | 25.00 | 100 |
| 3 | LED Ring Light | 59.00 | 5 |
| 4 | Oversized Hoodie | 45.00 | 30 |
| 5 | Phone Tripod | 19.50 | 3 |
| 6 | Matcha Starter Kit | 32.00 | 40 |

## API

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | | `{status, products}` |
| POST | `/api/reset` | | reloads seed data |
| GET | `/api/products` | | list of `{id, name, price, stock, emoji}` |
| POST | `/api/carts` | | cart (201) |
| GET | `/api/carts/{id}` | | cart |
| POST | `/api/carts/{id}/items` | `{product_id, qty}` | cart (adds to existing quantity) |
| PATCH | `/api/carts/{id}/items/{product_id}` | `{qty}` | cart (sets quantity) |
| DELETE | `/api/carts/{id}/items/{product_id}` | | cart |
| POST | `/api/carts/{id}/coupons` | `{code}` | cart |
| DELETE | `/api/carts/{id}/coupons/{code}` | | cart |
| POST | `/api/carts/{id}/checkout` | | `{order_id, total}` |

A cart is `{id, items: [{product_id, name, emoji, price, qty}], coupons: [code], subtotal, tier_discount, coupon_discount, total}`.
Errors are `{"detail": {"code": "...", "message": "..."}}`.
