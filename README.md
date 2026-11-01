# AI Test Platform

You type the rules of an app in plain English. AI writes tests for those rules, runs them, and tells you which rules the app breaks and which line of code to fix.

The app being tested is a small online shop (`shop/`) with 3 planted bugs (`docs/seeded-defects.md`).

## Who it is for, and what it covers

**Users:** developers and QA people on a product team (for example an e-commerce team like TikTok Shop) who have written business rules and want them tested quickly, without writing every test by hand.

**Problem:** writing tests by hand is slow. Asking an AI to write them is fast, but the AI makes mistakes. You get fake bug reports, missed bugs, and no way to tell which failures are real.

**In scope:** rules for a web API (a backend that answers requests), written in plain English. The tool covers:

- turning the rules into tests;
- running them on a fresh copy of the app;
- deciding bug vs. wrong test vs. unstable;
- pointing to the faulty line;
- retesting after a fix.

**Out of scope:**

- clicking through a website;
- speed and load tests;
- many users acting at the same time;
- large codebases;
- logins.

## How it works

1. **You** type the rules in plain English.
2. **AI** turns them into numbered rules (R1, R2…) and asks about anything unclear.
3. **AI** writes tests from the rules only. It never sees the code at this stage.
4. **A second AI** checks each test blind: it works out the answers without seeing the test's answers. Tests it disagrees with are left out.
5. **Code** starts a fresh copy of the shop, runs every test 3 times, and decides pass or fail.
6. **AI** looks at each test that failed all 3 times: it reads the rules, the failure and the code, and decides whether the code or the test is wrong.
7. **You** fix the code and run the same tests again.

Every test ends with one label:

| Label            | Meaning                                                                            | Who decides                                   |
| ---------------- | ---------------------------------------------------------------------------------- | --------------------------------------------- |
| **PASS**         | The shop follows the rule                                                          | Code                                          |
| **BUG**          | The code breaks the rule. Shows the faulty line and a suggested fix                | AI judges; code checks the line really exists |
| **BAD_TEST**     | The test was wrong. The AI rewrote it and the new test passed                      | AI rewrites; code reruns it                   |
| **NEEDS_REVIEW** | It failed every time, but the AI can't prove whether the code or the test is wrong | A human                                       |
| **UNSTABLE**     | The 3 runs gave different results (e.g. pass, fail, pass)                          | Code; a human looks. Never counted as a pass  |
| **ENV_ERROR**    | The shop was down or unreachable, so the test could not be judged                  | Code                                          |

**AI** writes, reviews and judges. **Code** runs the tests, decides pass/fail, and checks that the line the AI blames really exists. **A human** fixes bugs and decides anything the AI is unsure about.

## The 3 planted bugs

All three are code logic mistakes: the code does something different from what the rules say. The tests are written only from the rules, so they expect the right behaviour, and the buggy code fails them.

| Bug | Rule (`specs/shop-requirements.md`)         | What the code does wrong                                                 | Tests that caught it | AI judge pointed to  |
| --- | ------------------------------------------- | ------------------------------------------------------------------------ | -------------------- | -------------------- |
| B1  | R1: $100 or more gets 10% off               | Uses `>` instead of `>=`, so exactly $100 gets no discount               | R1-02, R6-03         | `shop/pricing.py:24` |
| B2  | R2: only one coupon per order               | Only blocks the _same_ coupon twice; two different coupons are accepted  | R2-01                | `shop/app.py:182`    |
| B3  | R4: a failed checkout must not change stock | Removes stock item by item, so items before the failing one stay removed | R4-03                | `shop/app.py:220`    |

Details and how to see each bug by hand: `docs/seeded-defects.md`. That file is never shown to the AI.

## How the second reviewer works

A different model (Gemini 3 Flash) checks each test before it runs, like a teacher marking homework without looking at the answers first:

1. It gets the rules and the test's steps, with the expected values hidden: "add 4 Glow Serums ($100) → discount = ?".
2. It works out each value itself from the rules.
3. Our code compares its answers with the test's. If they match, the test is kept. If they differ, the test is flagged and left out (or shown to a person if approval is turned on).

It is blind on purpose: when the reviewer could see the answers, it agreed with everything, even tests I had broken on purpose. It catches wrong tests _before_ they run, including ones that would wrongly pass. Example: "$100 gets $0 off" passes on the buggy shop, because the bug gives $0 too.

## Main parts

| Part                                                                | File                                                  | AI or code?                             |
| ------------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------- |
| Turn typed text into numbered rules, ask questions                  | `tester/requirements.py`                              | AI                                      |
| Write tests as filled-in forms                                      | `tester/generator.py`, form in `tester/dsl.py`        | AI                                      |
| Reject broken forms (unknown rule, unknown page, checks nothing)    | `tester/lint.py`                                      | code                                    |
| Blind second review                                                 | `tester/review.py`                                    | AI predicts, code compares              |
| Start a fresh shop with its own database                            | `tester/env.py`                                       | code                                    |
| Send the requests, decide pass/fail per check                       | `tester/engine.py`                                    | code                                    |
| Run every test 3 times, decide the verdict                          | `tester/runner.py`                                    | code                                    |
| Judge a failure: code, test or unsure; check the blamed line exists | `tester/triage.py`                                    | AI judges, code verifies                |
| Fix a wrong test                                                    | `tester/repair.py`                                    | AI rewrites, code re-checks and re-runs |
| Report, screen, terminal                                            | `tester/report.py`, `ui/app.py`, `tester/__main__.py` | code                                    |
| One place for every AI call: log, fallback model, saved answers     | `tester/llm.py`                                       | code                                    |

## Where each prompt is

Every AI step has its prompt at the top of its file, in two parts: `SYSTEM` (the AI's role) and `PROMPT` (the message, with the rules and test filled in). Click a file to open the prompt.

| AI step                       | Prompt                                               | Model            | What goes in                                                                 | What comes out                                                                                        |
| ----------------------------- | ---------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 1. Turn typed text into rules | [tester/requirements.py](tester/requirements.py#L29) | Gemini 3.5 Flash | What you typed                                                               | Numbered rules (R1, R2…), plus up to 2 plain questions if something is unclear                        |
| 2. Write the tests            | [tester/generator.py](tester/generator.py#L14)       | Gemini 3.5 Flash | The rules only, never the code                                               | Tests as filled-in forms; every check names its rule and why                                          |
| 3. Blind second review        | [tester/review.py](tester/review.py#L23)             | Gemini 3 Flash   | The rules, and each test with its expected values hidden                     | Its own answer for each hidden value; code then compares the two                                      |
| 4. Judge a failure            | [tester/triage.py](tester/triage.py#L20)             | Gemini 3.5 Flash | The rules, the failed check (expected vs actual) and the shop's code         | Who is wrong (code, test or unsure), the exact line, and a suggested fix; code checks the line exists |
| 5. Repair a wrong test        | [tester/repair.py](tester/repair.py#L22)             | Gemini 3.5 Flash | The rules, the wrong test, what the shop returned, and the judge's reasoning | A corrected test, or "keep" if it thinks the test was right; code re-checks and reruns it             |
| Old v1 (not used now)         | [tester/v1_codegen.py](tester/v1_codegen.py#L16)     | Gemini 3.5 Flash | The rules                                                                    | A whole pytest file; replaced by the form (see "How the idea changed")                                |

Every prompt actually sent, and the answer, is also saved locally to `runs/llm_calls.jsonl`. That file is not in the repo.

## Two key decisions

**1. Tests are a form the AI fills in, not code the AI writes** (`tester/dsl.py`)

- **Other option:** let the AI write test code (version 1 did this).
- **Why:**
  - our code can check a form before running it;
  - every expected value must name a rule;
  - only our code runs anything.
- **Trade-off:** tests can only do what the form allows (API calls and value checks). A new kind of test needs a new form and a runner for it.

**2. An AI judge decides bug vs. wrong test** (`tester/runner.py`, `tester/triage.py`)

- **Other option:** run every test on a known bug-free copy, so code alone decides (built first, then removed).
- **Why:** a bug-free copy rarely exists in real life, and never for a new feature.
- **Trade-off:** the verdict is now an AI judgement, not a fact. To limit that:
  - code still decides every pass/fail;
  - a BUG needs the blamed line to really exist;
  - a BAD_TEST needs the AI's rewritten test to pass;
  - everything else goes to a human.

## Design point of view

**AI suggests, code verifies, people decide what is uncertain. The tool never hides uncertainty.** You can see this in the screen and the report:

- every verdict has its own label (UNSTABLE, NEEDS_REVIEW, ENV_ERROR) instead of a forced pass or fail;
- a pass on a rerun is never shown as a pass;
- AI fix suggestions are marked "advice only" with "location verified" or "not verified";
- each AI step shows whether its answer was live or saved;
- raw requests and responses are always one click away.

"How the idea changed" below is the design iteration.

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

Also this is extendable to any other test cases by changing the format of the template.

**2. The local second reviewer was not accurate enough.** I wanted a second AI to double-check every test, and first tried a free local model (Qwen via Ollama).

- When it could see the test's answers, it agreed with everything, even tests I broke on purpose.
- I made it blind: it works out its own answers and code compares them. It then caught all broken tests.
- But even after 4 rounds of improving the prompt, it still wrongly flagged 9 of 26 correct tests.
- A bigger version was worse (11) and 25× slower.
- So I switched the reviewer to Gemini 3 Flash: it catches all broken tests and wrongly flags 0. (`docs/review-tuning.md`)

This itself is another limitation as the model is reviewing another Gemini model. Ideally we should use either claude/chatgpt but due to APIs not being free I was unable to test it.

**3. Comparing with a bug-free copy was unrealistic.** To tell "bug" from "bad test", I first ran every test on a saved bug-free copy of the shop too. If a test failed there as well, the test was wrong.

- This worked, but in real life you rarely have a bug-free copy, and never for a new feature.
- So I replaced it with an AI judge that reads the code when a test fails. It still put all 3 bugs at the right line. (`docs/ai-judge.md`)

**4. Smaller changes**

- Wrong tests used to be thrown away; now the AI fixes its own test.
- Human approval of tests is now optional: tests the reviewer flags are left out automatically.

## What I reused, changed and built

|                    | What                                                                                                                                                                                                                                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Reused as-is**   | FastAPI, Uvicorn, SQLite (the shop); httpx (sending requests); Pydantic (the test form); Streamlit + pandas (the screen); pytest; python-dotenv; Google's `google-genai` library with Gemini 3.5 Flash (writes tests, judges failures, repairs tests) and Gemini 3 Flash (reviewer); Ollama + Qwen 2.5 (tried as reviewer, dropped) |
| **Changed**        | Nothing was forked. The only borrowed idea is the standard practice of rerunning tests to spot flakiness.                                                                                                                                                                                                                           |
| **Built by me**    | The shop and its 3 planted bugs; the test form and linter; the test runner; the blind review method; the AI judge and its line check; the self-repair loop; the 3× reruns; the report, screen and terminal tool; all prompts                                                                                                        |
| **AI coding tool** | Claude Code helped write the code. I made the product decisions and corrected it along the way (see "How the idea changed").                                                                                                                                                                                                        |

**Most valuable contribution:** "ask an AI to write tests from the requirements" is the obvious idea, and on its own it isn't accurate enough. My contribution is two simple additions that made a measurable difference:

- **Tests as a JSON form, not free code.** Free test code gave 5 fake bug reports and missed 1 of the 3 bugs. With the form, every check names its rule: 0 fake reports, 3 of 3 bugs found. (The prompt also changed between the two versions, so this is not a perfectly controlled comparison.)
- **A blind second model.** A reviewer that could see the answers agreed with everything, even broken tests. With the answers hidden, it caught 3 of 3 broken tests and raised 0 false alarms on 26 good ones.

Everything else follows the same idea: the AI suggests, and code checks it (the blamed line exists, the repaired test passes, the 3 runs agree).

## Run it

**Version:** git tag `v1.0`. Python 3.12. Libraries are in `requirements.txt`. Gemini needs a free API key.

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

Every AI call is logged in `runs/llm_calls.jsonl`.

Try the random-failure switch: `SHOP_FLAKY=0.3 python -m tester run`.

## What is real, simulated, pre-generated or recorded

| Label               | What                                                                                                                                                                        |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Real**            | Every test run (real requests to a real shop on your machine) and every live AI call                                                                                        |
| **Simulated**       | The 3 bugs (planted on purpose); the 3 broken tests in `generated/broken/` (planted AI mistakes); random checkout failures (`SHOP_FLAKY`, `shop/chaos.py`)                  |
| **Pre-generated**   | `generated/v2/suite.json` (tests written by Gemini earlier). The example requirements reuse AI answers saved earlier, to save free API quota. Anything typed is always live |
| **Recorded**        | Everything in `evidence/`: saved runs with raw results, reports and server logs                                                                                             |
| **Screen-recorded** | Nothing                                                                                                                                                                     |

## Limitations

- **The reviewer and the writer are both Gemini,** so they may share blind spots. Free APIs from other vendors were not available to test.
- **The AI judge reads a fixed list of 3 files.** A large codebase would need the AI to search for the right files itself.
- **Only API tests with exact values.** No website clicks, speed, or many users at once.
- **Flakiness that shows up less than once in 3 runs** can be missed. A real bug that also fails randomly shows as UNSTABLE, not BUG.
- **Tested on one small shop with 3 planted bugs.** The numbers here are evidence, not a benchmark.

## Unfinished parts

- **The AI judge can't look for files itself.** It is given 3 fixed files; a real codebase needs it to search for the right ones. This is where there's potential for another agent to search for the relevant files before sending them for evaluation.
- **The test form only covers API value checks.** Speed or website tests would need a new form and a runner for it.
- **UNSTABLE doesn't say which run was different.** All attempts are saved, but you have to compare them yourself.

## Proof

| Folder                         | What it shows                                               |
| ------------------------------ | ----------------------------------------------------------- |
| `evidence/retest/`             | Bug found → one-line fix → same tests pass                  |
| `evidence/ai-judge/`           | AI judge on the real tests and on 3 broken ones             |
| `evidence/review/`             | Qwen (7B, 14B) vs Gemini as reviewer                        |
| `evidence/repair/`             | AI fixing tests I broke on purpose                          |
| `evidence/flaky/`              | Simulated random checkout failures marked UNSTABLE, not BUG |
| `evidence/v1/`, `evidence/v2/` | Raw results before and after idea 1                         |
