"""Pricing rules. Pure functions, no database access.

R1  Orders with a subtotal of $100.00 or more get 10% off.
R2  Only one coupon can be used per order (enforced in the API).
"""

from decimal import ROUND_HALF_UP, Decimal

TIER_THRESHOLD = Decimal("100.00")
TIER_RATE = Decimal("0.10")
CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def subtotal(lines) -> Decimal:
    """lines: iterable of (unit_price, qty)."""
    return money(sum((Decimal(price) * qty for price, qty in lines), Decimal("0")))


def tier_discount(sub: Decimal) -> Decimal:
    if sub >= TIER_THRESHOLD:
        return money(sub * TIER_RATE)
    return money(0)


def coupon_discount(sub: Decimal, coupons) -> Decimal:
    """coupons: iterable of (kind, value). Each coupon is based on the subtotal."""
    total = Decimal("0")
    for kind, value in coupons:
        if kind == "percent":
            total += sub * Decimal(value) / 100
        else:
            total += Decimal(value)
    return money(total)


def quote(lines, coupons):
    sub = subtotal(lines)
    tier = tier_discount(sub)
    coupon = coupon_discount(sub, coupons)
    total = max(sub - tier - coupon, money(0))
    return {
        "subtotal": sub,
        "tier_discount": tier,
        "coupon_discount": coupon,
        "total": money(total),
    }
