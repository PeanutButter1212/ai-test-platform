"""Simulated AI mistakes: copy 3 correct tests and break one expectation in each.

    python scripts/make_broken_suite.py      # writes generated/broken/suite.json
    python -m tester run --suite generated/broken/suite.json

Used to show that wrong tests are caught on the known-good baseline and
repaired by the AI. The mistakes are planted by hand, not made by the AI.
"""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISTAKES = [  # test id, field, wrong value
    ("R1-02", "tier_discount", "0.00"),        # $100 gets no discount (should be 10.00)
    ("R5-02", "coupon_discount", "10.00"),     # LESS5 takes $10 off (should be 5.00)
    ("R3-02", "detail.code", "OUT_OF_STOCK"),  # wrong error code (should be QTY_RANGE)
]

suite = json.loads((ROOT / "generated" / "v2" / "suite.json").read_text())
by_id = {e["test"]["id"]: e for e in suite["accepted"]}
broken = []
for test_id, field, wrong in MISTAKES:
    entry = copy.deepcopy(by_id[test_id])
    check = next(c for s in entry["test"]["steps"] for c in s["checks"] if c["field"] == field)
    check["value"] = wrong
    broken.append(entry)

out = ROOT / "generated" / "broken" / "suite.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({**suite, "accepted": broken, "note": "3 hand-broken copies of v2 tests (simulated)"},
                          indent=2, ensure_ascii=False))
print(out)
