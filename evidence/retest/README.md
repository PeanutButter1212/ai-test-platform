# Retest after fixing B1 (recorded run)

The same 26 tests (`generated/v2/suite.json`) ran before and after a one-line fix to `shop/pricing.py`.
Both runs are real executions on a fresh shop instance. Failures were judged by the AI judge (see `docs/ai-judge.md`).

| | B1 tests (R1-02, R6-03) | All tests |
|---|---|---|
| Before (`before/`) | ❌ BUG: `tier_discount` expected 10.00, got 0.00 | PASS 22 · BUG 4 |
| Fix (`fix.diff`) | `if sub > TIER_THRESHOLD:` → `if sub >= TIER_THRESHOLD:` | |
| After (`after/`) | ✅ PASS | PASS 24 · BUG 2 |

The AI's diagnosis in the before run pointed at `shop/pricing.py:24` and suggested this exact change (see `before-cli.txt`).
B2 (R2-01) and B3 (R4-03) were not fixed and are still reported after the retest, as expected.

After recording, the fix was reverted so the bug can be fixed live in the demo.
Each folder has `results.json` (raw requests and responses), `report.html` and the server log.
Re-recorded after the switch to the AI judge; the earlier baseline-mode recording is in git history.
