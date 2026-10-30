# Seeded defects

These bugs were planted **on purpose** so the testing platform has known problems to find.
Each one was added in its own commit, and each fix will also be its own commit.

> This file is ground truth for evaluating the platform. It is never given to the AI.

| ID | Rule broken | What goes wrong | Where | Planted in |
|---|---|---|---|---|
| B1 | R1 | A subtotal of exactly $100.00 gets no spend discount (`>` instead of `>=`) | `shop/pricing.py`, `tier_discount` | `chore(seed): plant defect B1 …` |
| B2 | R2 | Two different coupons can be applied to one order; only the same code twice is blocked | `shop/app.py`, `apply_coupon` | `chore(seed): plant defect B2 …` |
| B3 | R4 | A checkout that fails with `OUT_OF_STOCK` still removes stock for items checked before the failing one | `shop/app.py`, `checkout` | `chore(seed): plant defect B3 …` |

## Reference versions

- `shop-clean` (git tag): the bug-free shop, used as the known-good baseline.
- `main` after the seed commits: the buggy shop that the platform tests.

## How to see each bug by hand

- **B1:** add 4 × Glow Serum ($100.00). The spend discount shows $0.00 instead of $10.00.
- **B2:** apply `SAVE10`, then `LESS5`. Both are accepted.
- **B3:** add 2 × Wireless Earbuds and 4 × Phone Tripod (only 3 in stock), then check out. Checkout fails, but Earbuds stock drops from 50 to 48.
