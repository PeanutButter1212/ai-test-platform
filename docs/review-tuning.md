# Second-model review: how it was tuned

**What it is:** Gemini writes the tests. A second model from a different vendor reviews them before they run. That model is Qwen 2.5 7B, running locally with Ollama, free and offline. Flagged tests go to a human; nothing is fixed automatically.

**How to check it works:** break 3 correct tests on purpose and see if the reviewer catches them (`scripts/check_reviewer.py`):

- R1-02: says $100 gets **no** discount (should be $10 off)
- R5-02: says LESS5 takes **$10** off (should be $5)
- R3-02: expects error **OUT_OF_STOCK** (should be QTY_RANGE)

The 26 real tests are known to be correct, because they all pass on the clean shop. So any flag on them is a false alarm.

## Iterations

| Version | What changed | Broken tests caught | False alarms on 26 real tests |
|---|---|---|---|
| 1. Show and ask | Reviewer sees the test, including expected values, and answers agree/disagree | **0 / 3** | 0 |
| 2. Blind review | Reviewer never sees the expected values. It predicts each value; **our code** compares (numbers matched by value, so `$10.00` = `10.00`). Success codes 200/201 are not reviewed because the rules don't specify them | 3 / 3 | 15 |
| 3. Fixed numbering | One named answer slot per check (`c1`, `c2`, …) instead of a free list the model misnumbered. Looser matching: `400 EMPTY_CART` = `EMPTY_CART`, `[]` = `0` | 3 / 3 | 14 |
| 4. Abstain | A blank or wrong-type answer (e.g. an error code where money is expected) counts as "no opinion", not a disagreement | **3 / 3** | **9** |

### What we learned

- **v1 rubber-stamped everything.** A small model shown an answer tends to agree with it. "Agree" from that design means nothing, and that's why the review must be blind.
- **Let code do the comparing.** The model only predicts; a deterministic comparison decides. The model also writes values in different formats, so the comparison has to be forgiving about format but strict about the value.
- **Remaining false alarms come from the model's reasoning, not our plumbing.** Examples:
  - it applies a rejected coupon anyway (R2-01);
  - it lets a quantity of 21 into the cart even though R3 forbids it (R3-04);
  - it thinks a failed checkout still reduces stock (R4-02/R4-03).

  A 7B model loses track of state across several steps.

## Bigger model?

Same v4 reviewer, same checks, run with `qwen2.5:14b` (9 GB) on an M3 with 16 GB RAM:

| Model | Broken tests caught | False alarms on 26 real tests | Time for 26 tests |
|---|---|---|---|
| qwen2.5:7b | 3 / 3 | **9** | **~1 min** |
| qwen2.5:14b | 3 / 3 | 11 | ~27 min (about 57 s per test) |

The bigger model was not more accurate here. It misread R1 ("$119.70 gets no spend discount") and often answered with a sentence instead of a bare value. It was also about 25× slower, because a 9 GB model nearly fills 16 GB of RAM. **Decision: keep 7B.** Raw outputs are in `evidence/review/qwen2.5-14b/`.

## How it is used

- The review is a **filter for human attention**, not a judge. With 9 of 26 flagged, a person still has to look at about a third of the tests. They see the reviewer's reasoning next to each flag, so most false alarms are quick to dismiss.
- The stronger safety net is still the **baseline run**: a test that fails on the known-good shop is marked BAD_TEST whatever the reviewer said.

## Limitations and next options

- **Ask twice and only flag when both runs disagree with the test** (self-consistency). This doubles run time.
- The 3 broken tests are a small check, not a benchmark.

## Reproduce

```
ollama pull qwen2.5:7b
python -m tester review                      # writes "review" into each test in the suite
PYTHONPATH=. python scripts/check_reviewer.py  # the 3 broken tests
```

**Raw outputs:** `evidence/review/`. Every prompt and response is in `runs/llm_calls.jsonl`, and the cached responses in `llm_cache/` make reruns instant.
