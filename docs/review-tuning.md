# Second-model review: how it was tuned

**What it is:** Gemini 3.5 Flash writes the tests. A second model reviews them before they run, and flagged tests go to a human; nothing is fixed automatically.

**Outcome:** I first tried a free, local model (Qwen 2.5 7B and 14B via Ollama). It caught every broken test but raised too many false alarms, even after four rounds of improving the prompt and the comparison (the model itself was not retrained). So the default reviewer is now **Gemini 3 Flash**: 3/3 broken tests caught, 0 false alarms. The Ollama code was then removed; the Qwen results stay in `evidence/review/` as the record of the experiment.

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

The bigger model was not more accurate here. It misread R1 ("$119.70 gets no spend discount") and often answered with a sentence instead of a bare value. It was also about 25× slower, because a 9 GB model nearly fills 16 GB of RAM. **Decision: keep 7B.** Raw outputs are in `evidence/review/qwen2.5-14b/` (7B: `evidence/review/qwen2.5-7b/`).

## Switch to Gemini 3 Flash

Same v4 reviewer and checks, run with `gemini-3-flash-preview`:

| Reviewer | Broken tests caught | False alarms on 26 real tests | Time for 26 tests | Runs |
|---|---|---|---|---|
| qwen2.5:7b (local) | 3 / 3 | 9 | ~1 min | offline, free |
| qwen2.5:14b (local) | 3 / 3 | 11 | ~27 min | offline, free |
| **gemini-3-flash-preview** | **3 / 3** | **0** | ~3 min | cloud, free tier |

Gemini's reasoning was correct on the multi-step cases the local models got wrong. One call failed with `504 DEADLINE_EXCEEDED`; 504 is now treated like 503 and falls back to the next model.

**Trade-off:** the reviewer now comes from the same vendor as the generator, so it is less independent than a different vendor's model would be. Mitigations:
- it is a different model version (3 Flash reviews, 3.5 Flash writes);
- the review is blind;
- the baseline run still catches wrong tests whatever the reviewer says.

The free-tier quota also has to cover review calls. Raw outputs are in `evidence/review/gemini-3-flash-preview/`.

## How it is used

- The review is a **filter for human attention**, not a judge. Flagged tests are shown with the reviewer's reasoning so a person can decide.
- The stronger safety net is still the **baseline run**: a test that fails on the known-good shop is marked BAD_TEST whatever the reviewer said.

## Limitations and next options

- **Ask twice and only flag when both runs disagree with the test** (self-consistency). This doubles run time.
- The 3 broken tests are a small check, not a benchmark.

## Reproduce

```
python -m tester review                                           # Gemini 3 Flash; writes "review" into each test
PYTHONPATH=. python scripts/check_reviewer.py                    # the 3 broken tests
```

**Raw outputs:** `evidence/review/`. Every prompt and response is in `runs/llm_calls.jsonl`, and the cached responses in `llm_cache/` make reruns instant.
