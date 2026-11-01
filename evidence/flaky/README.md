# Flaky tests (simulated)

`SHOP_FLAKY=0.3 python -m tester run` runs the shop through `shop/chaos.py`, which makes about 30% of checkouts fail at random with `503 CHECKOUT_UNAVAILABLE`.
The shop's own code is unchanged. **The instability is simulated; the run itself is real.**

What the tool does:
- Every test runs 3 times, and every attempt is kept in `results.json`.
- Runs disagree (e.g. ❌ ✅ ❌ or ✅ ❌ ✅) → **UNSTABLE**: not judged, a human should look. A pass on a rerun never counts as a pass.
- Fails the same way every time → judged as usual (BUG / BAD_TEST / NEEDS_REVIEW).
- Fails only because the server answered 502/503/504 → **ENV_ERROR**, not judged. This was added after a test hit the random 503 three times in a row and the AI judge wrongly called it a BUG.

Limits:
- Flakiness that shows up less than once in 3 runs can still be missed.
- If a real bug's test hits a random failure on one attempt, it shows as UNSTABLE instead of BUG.
