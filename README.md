# Verdict

An AI-driven automated testing tool: AI reads plain-English requirements and writes tests, deterministic code runs them and decides pass/fail, and the report proves which bugs were found and fixed.

> 🚧 Work in progress — built incrementally, see commit history.

## Planned flow

1. **Requirements** — plain-English rules for the app under test
2. **AI writes tests** — each test traces back to a rule
3. **Run** — fresh app instance, deterministic assertions
4. **Report** — failures with evidence; flaky/environment issues labelled, never hidden
5. **Fix & retest** — old and new runs both kept as proof

## System under test

**ShopLite** — a small checkout API (cart, coupons, checkout) with intentionally seeded defects.
