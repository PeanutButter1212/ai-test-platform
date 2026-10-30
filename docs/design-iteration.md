# Design iteration: v1 (AI writes test code) → v2 (AI writes test data)

## v1: ask the LLM for a pytest file

`tester/v1_codegen.py` sends `specs/shop-requirements.md` to `gemini-3.5-flash` and asks for a runnable
pytest file. The output (`generated/v1/test_generated.py`, 329 lines, 30 test cases) was run unchanged
against two versions of the shop:

| Target | Result | Raw output |
|---|---|---|
| Buggy shop (`main` with B1–B3) | 7 failed, 23 passed | `evidence/v1/pytest-buggy.txt` |
| Bug-free shop (tag `shop-clean`) | 5 failed, 25 passed | `evidence/v1/pytest-clean.txt` |

The raw prompt and response are in `evidence/v1/llm-call.json`.

### What went wrong

Of the 7 failures on the buggy shop, only 2 were real defects (B1, B2). The other 5 also failed on the
bug-free shop, so they were wrong tests:

1. **Invented expectation (4 false alarms).** `test_r5_coupons_case_insensitive` asserts the cart echoes the
   coupon code in the caller's casing (`save10`). The spec never says that, and the shop returns `SAVE10`.
   The model's own comment shows it was unsure: `# or normalized code`.
2. **Self-contradicting oracle (1 false alarm).** `test_r7_checkout_success_reduces_stock` has a comment that
   correctly computes the total as 106.20, but asserts `118.00`.
3. **Missed defect B3.** The out-of-stock test uses a single-item cart, so the partial stock deduction bug
   never triggers. The test passes on broken code.
4. **No way to triage.** A plain pass/fail list cannot tell "the app is wrong" from "the test is wrong".
   Here we only knew because we had a bug-free version to compare against.

## What v2 changes, and why

| Problem in v1 | v2 response |
|---|---|
| Expectations not grounded in the spec | Tests are JSON data. Every check must cite a rule ID, and the linter rejects checks without one |
| Assertions hidden inside free-form code | Checks are declarative (`status`, `field equals`), so they can be shown in a table and reviewed |
| Wrong oracles look like bugs | Every test is first run against the known-good version; a test that fails there is marked a bad test, not a bug |
| Shallow tests miss bugs | The prompt asks for boundary and multi-item cases per rule; a second model reviews coverage |
| Arbitrary generated code is executed | Only our engine executes; the LLM output is data |

The cost: the DSL is less expressive than Python, and the engine is ours to build and maintain.
