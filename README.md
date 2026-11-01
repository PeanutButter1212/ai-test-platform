# AI Test Platform

You type the rules of an app in plain English. AI writes tests for those rules, runs them, and tells you which rules the app breaks and which line of code to fix.

The app being tested is a small online shop (`shop/`) with 3 planted bugs (`docs/seeded-defects.md`).

## How it works

```
You type requirements
→ AI turns them into numbered rules and asks about anything unclear
→ AI writes tests from the rules (it never sees the code at this stage)
→ a second AI checks each test blind (it works out the answers without seeing them)
→ code runs every test on a fresh copy of the shop and decides pass/fail
→ a failing test is rerun 2 more times; if the results change, it is UNSTABLE (a human looks)
→ for each failure, AI reads the rules + the failure + the code:
     code is wrong → BUG          (with the line and a suggested fix)
     test is wrong → BAD_TEST     (AI fixes its own test and reruns it)
     not sure      → NEEDS_REVIEW (a human decides)
→ developer fixes the code → run the same tests again
```

**AI** writes, reviews and judges. **Code** runs the tests, decides pass/fail, and checks that the line the AI blames really exists. **A human** fixes bugs and decides anything the AI is unsure about.

## How the idea changed

**1. Just asking AI for test code was not reliable.** First I asked the AI to write test code directly.

- Result: 5 fake bug reports, and it missed 1 of the 3 bugs.
- Fix: the AI now fills in a fixed test form instead of writing free code. A checker rejects bad tests, and every check must name the rule it comes from.
- Result: all 3 bugs found, 0 fake reports. (`docs/design-iteration.md`)

A real test the AI wrote (shortened, from `generated/v2/suite.json`):

```json
{
  "id": "R1-02",
  "rule": "R1",
  "title": "Subtotal exactly $100.00 qualifies for 10% spend discount",
  "steps": [
    { "method": "POST", "path": "/api/carts", "save_id_as": "cart" },
    {
      "method": "POST",
      "path": "/api/carts/{cart}/items",
      "body": { "product_id": 2, "qty": 4 },
      "checks": [
        {
          "field": "tier_discount",
          "op": "equals",
          "value": "10.00",
          "rule": "R1",
          "why": "Subtotal is exactly $100.00, so it qualifies for 10% off"
        }
      ]
    }
  ]
}
```

In words: make a cart, add 4 Glow Serums ($100), and check the discount is 10.00 because of rule R1. The AI can only fill in steps, checks, the rule and a reason.

Before, the AI wrote free code instead:

```python
def test_discount():
    cart = httpx.post(f"{BASE}/api/carts").json()["id"]
    ...
    assert r.json()["tier_discount"] == "10.00"
```

Free code can do anything, so it is hard to check and does not say which rule it tests. With the form:

- our code can check a test before running it (does the rule exist? does the page exist? does it check anything?);
- every expected value comes with a rule and a reason;
- our code runs the test, not the AI's code.

The form is defined in `tester/dsl.py`.

Also this is extendable to any other test cases by changign the format of the template.

**2. The local second reviewer was not accurate enough.** I wanted a second AI to double-check every test, and first tried a free local model (Qwen via Ollama).

- When it could see the test's answers, it agreed with everything, even tests I broke on purpose.
- I made it blind: it works out its own answers and code compares them. It then caught all broken tests.
- But even after 4 rounds of improving the prompt, it still wrongly flagged 9 of 26 correct tests.
- A bigger version was worse (11) and 25× slower.
- So I switched the reviewer to Gemini 3 Flash: it catches all broken tests and wrongly flags 0. (`docs/review-tuning.md`)

This itself is another limitation as the model is reviewing another Gemini mode. Ideally we should use either claude/chatgpt but due to APIs not being free I was unable to test it.

**3. Comparing with a bug-free copy was unrealistic.** To tell "bug" from "bad test", I first ran every test on a saved bug-free copy of the shop too. If a test failed there as well, the test was wrong.

- This worked, but in real life you rarely have a bug-free copy, and never for a new feature.
- So I replaced it with an AI judge that reads the code when a test fails. It still put all 3 bugs at the right line. (`docs/ai-judge.md`)

**4. Smaller changes**

- Wrong tests used to be thrown away; now the AI fixes its own test.
- Human approval of tests is now optional: tests the reviewer flags are left out automatically.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add a free Gemini API key
```

| What                 | Command                                                 | Opens                 |
| -------------------- | ------------------------------------------------------- | --------------------- |
| The shop             | `uvicorn shop.app:app --reload`                         | http://localhost:8000 |
| The testing screen   | `python -m streamlit run ui/app.py`                     | http://localhost:8501 |
| Or from the terminal | `python -m tester generate` then `python -m tester run` | report in `runs/`     |
| Unit tests           | `pytest`                                                |                       |

AI answers are saved in `llm_cache/`, so repeating the same request costs nothing. Every AI call is logged in `runs/llm_calls.jsonl`.

## Proof

| Folder                         | What it shows                                   |
| ------------------------------ | ----------------------------------------------- |
| `evidence/retest/`             | Bug found → one-line fix → same tests pass      |
| `evidence/ai-judge/`           | AI judge on the real tests and on 3 broken ones |
| `evidence/review/`             | Qwen (7B, 14B) vs Gemini as reviewer            |
| `evidence/repair/`             | AI fixing tests I broke on purpose              |
| `evidence/flaky/`              | Simulated random checkout failures marked UNSTABLE, not BUG |
| `evidence/v1/`, `evidence/v2/` | Raw results before and after idea 1             |
