"""v2: the LLM generates tests as structured data, one rule at a time."""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .dsl import TestSuite
from .lint import lint, parse_rule_ids
from .llm import LLM, LLMError

SYSTEM = """You are a senior QA engineer. You design API tests that find real defects.
Only expect values that the requirements state or that follow from them by arithmetic.
Never guess behaviour the requirements do not specify; if a value is unspecified, do not check it."""

PROMPT = """Requirements of the system under test:

{spec}

Write 3 to 5 test cases for rule {rule} only. Include normal, boundary and error cases where they apply.

How tests run:
- Before each test the shop is reset to the seed data above, so stock and prices are known.
- Steps run in order. Create a cart with POST /api/carts and save_id_as "cart", then use {{cart}} in paths.
- After a step, expect_status checks the HTTP status and checks inspect fields of the JSON response.
- Field paths: "total", "detail.code", "items.0.qty", "coupons", or "[id=5].stock" to pick an item from a list.
- Write every expected value as a string exactly as the API returns it (money like "10.00", status like "409").
- Every check must cite the rule it comes from and say why the value is expected.

Good tests also verify side effects: after an operation succeeds or fails, read the state back
and check it is what the rules say, not just the immediate response."""


def generate(spec_path: str, rules: list[str] | None = None, llm: LLM | None = None) -> dict:
    spec = Path(spec_path).read_text()
    rule_ids = parse_rule_ids(spec)
    llm = llm or LLM()
    accepted, rejected, failures = [], [], []

    for rule in sorted(rules or rule_ids, key=lambda r: int(r[1:])):
        try:
            raw = llm.generate(PROMPT.format(spec=spec, rule=rule), system=SYSTEM,
                               schema=TestSuite, purpose=f"v2-generate-{rule}")
            suite = TestSuite.model_validate_json(raw)
        except (LLMError, ValidationError) as exc:
            failures.append({"rule": rule, "error": str(exc)[:500]})
            continue
        for test in suite.tests:
            test.id = _unique_id(test.id, rule, accepted + rejected)
            problems = lint(test, rule_ids)
            entry = {"test": test.model_dump(), "lint": problems}
            (rejected if problems else accepted).append(entry)

    return {"spec": spec_path, "model": llm.model, "accepted": accepted,
            "rejected": rejected, "generation_failures": failures}


def _unique_id(proposed: str, rule: str, existing: list[dict]) -> str:
    taken = {e["test"]["id"] for e in existing}
    if re.fullmatch(rf"{rule}-\d+", proposed) and proposed not in taken:
        return proposed
    n = 1
    while f"{rule}-{n:02d}" in taken:
        n += 1
    return f"{rule}-{n:02d}"


def save(suite: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(suite, indent=2, ensure_ascii=False))
    return path
