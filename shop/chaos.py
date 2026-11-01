"""Simulated instability for testing the tester: not part of the shop.

Wraps the shop so checkout randomly fails with 503, like a payment provider timing out.
The fraction of failing checkouts comes from SHOP_FLAKY (e.g. 0.3).

    SHOP_FLAKY=0.3 uvicorn shop.chaos:app
"""

import os
import random

from fastapi import Request
from fastapi.responses import JSONResponse

from .app import app

FAIL_RATE = float(os.environ.get("SHOP_FLAKY", "0"))


@app.middleware("http")
async def flaky_checkout(request: Request, call_next):
    if request.url.path.endswith("/checkout") and random.random() < FAIL_RATE:
        return JSONResponse(status_code=503, content={"detail": {
            "code": "CHECKOUT_UNAVAILABLE", "message": "Simulated: checkout timed out, try again"}})
    return await call_next(request)
