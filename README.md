# AI Test Platform

An AI-driven automated testing tool: AI reads plain-English requirements and writes tests, deterministic code runs them and decides pass/fail, and the report proves which bugs were found and fixed.

> 🚧 Work in progress, built incrementally (see commit history).

## Planned flow

1. **Requirements**: plain-English rules for the app under test
2. **AI writes tests**: each test traces back to a rule
3. **Run**: fresh app instance, deterministic assertions
4. **Report**: failures with evidence; flaky/environment issues labelled, never hidden
5. **Fix & retest**: old and new runs both kept as proof

## System under test

A small online shop (`shop/`): product feed, cart, a spend-$100 discount, coupons and limited stock at checkout.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the shop

```bash
uvicorn shop.app:app --reload
```

Open http://localhost:8000 for the storefront. API docs are at http://localhost:8000/docs.
The database resets to seed data on every start (`SHOP_DB` sets its path, default `shop.db`).

## Run the testing platform

Copy `.env.example` to `.env` and add a Gemini API key (free tier works).

```bash
python -m tester generate      # AI reads specs/shop-requirements.md and writes tests
python -m tester run           # runs them on the known-good shop and the current shop
```

`run` prints a verdict per test and writes `runs/<timestamp>/report.html`:

| Verdict | Meaning |
|---|---|
| `BUG` | passes on the known-good version (`shop-clean` tag), fails on the current shop |
| `BAD_TEST` | fails on the known-good version, so the test itself is wrong |
| `ENV_ERROR` | the shop could not be started or reached; nothing is judged |
| `PASS` | passes on both |

Set `LLM_REPLAY=1` to reuse cached AI responses without calling the API.

## Tests

```bash
pytest
```
