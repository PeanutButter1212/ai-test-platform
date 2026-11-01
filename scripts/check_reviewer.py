"""Does the reviewer catch wrong tests? Break 3 correct tests on purpose and review them.

    PYTHONPATH=. python scripts/check_reviewer.py [MODEL]
"""

import json, copy, sys
from pathlib import Path
from tester.review import review_test
from tester.llm import LLM
suite = json.loads(Path("generated/v2/suite.json").read_text())
spec = Path(suite["spec"]).read_text()
from tester.review import DEFAULT_GEMINI_MODEL
llm = LLM(model=sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GEMINI_MODEL,
          cache=True)  # the broken tests are copies of the example suite
tests = {e["test"]["id"]: e["test"] for e in suite["accepted"]}
def mutate(tid, field, new, note):
    t = copy.deepcopy(tests[tid])
    for s in t["steps"]:
        for c in s["checks"]:
            if c["field"] == field:
                c["value"] = new
                r = review_test(t, spec, llm)
                print(f"{note}: {r.get('verdict')}\n  " + "\n  ".join(r.get('issues') or [r.get('error','')]))
                return
mutate("R1-02", "tier_discount", "0.00", "WRONG R1-02 $100 no discount")
mutate("R5-02", "coupon_discount", "10.00", "WRONG R5-02 LESS5 $10 off")
mutate("R3-02", "detail.code", "OUT_OF_STOCK", "WRONG R3-02 error code")
