# Judging failures: from a known-good copy to an AI judge

## The question
When a test fails, either the app is wrong (a bug) or the AI-written test is wrong. Something has to decide which.

## Before: compare with a known-good copy
Every test ran twice: on the current code and on a saved bug-free version (git tag `shop-clean`).
- Fails only on the current code → BUG.
- Fails on the good copy too → the test is wrong.

Code decided everything. The catch is that it needs a version known to be correct. For a new feature, or for a bug that has always been there, no such version exists. **Dropped as unrealistic.**

## Now: an AI judge
Every test runs once on the app, and code decides pass or fail for each check. For each failing test, an AI reads three things: the requirements, the failed checks (expected vs actual, raw requests and responses) and the app's source code. It answers *code*, *test* or *unclear*.

| AI answer | Extra check by code | Verdict |
|---|---|---|
| code | the quoted code really is in the named file | **BUG**, with location and a suggested fix |
| code | quoted code not found | **NEEDS_REVIEW** |
| test | AI rewrites the test, citing a rule; linted and re-run; it passes | **BAD_TEST** (repaired) |
| test | still fails after 2 attempts, or AI decides to keep it | **NEEDS_REVIEW** |
| unclear | – | **NEEDS_REVIEW** |
| (request failed) | – | **ENV_ERROR** |

The AI never sees the code while *writing* tests, only when *judging* a failure. That way tests come from the requirements and cannot copy a bug.

## Results (`evidence/ai-judge/`)

**The 26 generated tests on the buggy shop:** PASS 22 · BUG 4 · BAD_TEST 0 · NEEDS_REVIEW 0. All 3 planted bugs were judged BUG at the right line:
- B1 at `pricing.py:24`
- B2 at `app.py:182`
- B3 at `app.py:220`

**3 hand-broken tests (simulated AI mistakes, `generated/broken/`) on the buggy shop:**
- R5-02 (LESS5 = $10) → **BAD_TEST**, repaired to 5.00.
- R3-02 (wrong error code) → **BAD_TEST**, repaired to QTY_RANGE.
- R1-02 (`tier_discount` 0.00 at $100) → **BUG**. Correct, but worth noting: the planted wrong value *agrees* with bug B1, so that check passed. The test's other check (`total` 90.00) still failed and exposed B1. A wrong test can hide a bug when it makes the same mistake as the code.

## Trade-offs
- **Gained:** works without any known-good version, including for new features; one shop instance per run instead of two.
- **Lost:** "bug or bad test" is now an AI judgement, not a fact. Mitigations:
  - code still decides every pass/fail;
  - a BUG verdict needs the quoted code to exist;
  - a BAD_TEST verdict needs a rule-justified rewrite that passes;
  - everything else goes to a human.
- **Cost:** one AI call per failing test, plus repair calls. All of them are logged in `runs/llm_calls.jsonl` and cached.
- **Limit:** the AI reads a fixed list of source files (`tester/triage.py`). A large codebase would need it to search for the relevant files instead.
