"""Self-repair for wrong tests: a test that fails on the known-good baseline goes back to the AI.

The AI gets the rule, its test and the baseline's actual responses, and must
decide: either the test misread the rule (rewrite it), or the test follows the
rule and the baseline disagrees (keep it and flag for a human). A rewrite is
linted and re-run on the baseline; after MAX_ATTEMPTS it is left for a human.
Copying the baseline's values without a rule to justify them is not allowed,
because that would make every test pass by definition.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .dsl import TestCase
from .engine import run_test
from .lint import lint, parse_rule_ids
from .llm import LLM, LLMError

MAX_ATTEMPTS = 2

SYSTEM = """You are a senior QA engineer fixing your own test. The application version it ran
against is known to be correct. Decide honestly whether the test or the requirement is at fault.
Only change an expectation when the rule, read carefully, supports the new value."""

PROMPT = """Requirements:

{spec}

Your test {test_id} failed on the known-good version of the application.

Test (JSON):
{test}

Failed checks (expected by the test vs actual on the known-good version):
{failed}

Requests and responses on the known-good version:
{steps}

If the test misread or over-assumed the requirements, choose "rewrite" and return the corrected
test (same id and rule; every check must still cite a rule and explain why). If the test follows
the requirements and the application disagrees with them, choose "keep" and explain."""


class Repair(BaseModel):
    diagnosis: str = Field(description="Which expectation was wrong and why, citing the rule")
    decision: Literal["rewrite", "keep"]
    test: TestCase | None = Field(None, description="The corrected test when decision is 'rewrite'")


def _failure_context(record: dict) -> tuple[str, str]:
    failed = [f"- step {n}: {c['field']} {c['op']} {c['expected']!r}, actual {c['actual']!r}"
              for n, s in enumerate(record["steps"], 1) for c in s["checks"] if not c["passed"]]
    steps = "\n".join(
        f"{n}. {s['request']['method']} {s['request']['path']} {json.dumps(s['request']['body'])}"
        f" -> {s['response']['status']} {json.dumps(s['response']['body'])[:600]}"
        for n, s in enumerate(record["steps"], 1))
    return "\n".join(failed), steps


def repair_test(test: TestCase, record: dict, spec: str, base_url: str, llm: LLM) -> tuple[TestCase, dict, list]:
    """Try to fix one test that failed on the baseline. Returns (final test, final record, attempt history)."""
    rule_ids = parse_rule_ids(spec)
    history = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        failed, steps = _failure_context(record)
        prompt = PROMPT.format(spec=spec, test_id=test.id, test=test.model_dump_json(indent=1, exclude_none=True),
                               failed=failed, steps=steps)
        entry = {"attempt": attempt, "before": test.model_dump()}
        history.append(entry)
        try:
            raw = llm.generate(prompt, system=SYSTEM, schema=Repair, purpose=f"repair-{test.id}-{attempt}")
            fix = Repair.model_validate_json(raw)
        except (LLMError, ValidationError) as exc:
            entry["outcome"] = "error"
            entry["error"] = str(exc)[:500]
            break
        entry["diagnosis"], entry["decision"] = fix.diagnosis, fix.decision
        if fix.decision == "keep" or fix.test is None:
            entry["outcome"] = "kept for human review"
            break
        candidate = fix.test.model_copy(update={"id": test.id, "rule": test.rule})
        entry["after"] = candidate.model_dump()
        problems = lint(candidate, rule_ids)
        if problems:
            entry["outcome"] = "rejected by linter"
            entry["lint"] = problems
            continue
        test, record = candidate, run_test(candidate, base_url)
        entry["outcome"] = "passes on baseline" if record["passed"] else "still fails on baseline"
        if record["passed"] or record["error"]:
            break
    return test, record, history
