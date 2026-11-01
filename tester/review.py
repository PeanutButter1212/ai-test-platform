"""Second-model review: a different model checks each generated test before it runs.

Gemini 3.5 Flash writes the tests; a different model (Gemini 3 Flash)
independently predicts every expected value.
The review is blind: the reviewer never sees the test's expected values or the
reasons given for them, because a model shown an answer tends to agree with it.
Our code compares the two answers; mismatches are flagged for the human
approval step, never auto-fixed.
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, create_model

from .llm import LLM, LLMError
from .requirements import is_example

# A different model from the generator (gemini-3.5-flash), so it does not share its exact blind spots.
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

SYSTEM = """You are a careful QA engineer. Predict exactly what an API returns, using only
the requirements and seed data. Calculate money step by step."""

PROMPT = """Requirements:

{spec}

Before the test the shop is reset to the seed data. These requests run in order:
{steps}

Predict each check below. Work through the requests in order and track the cart and stock
after each one. Give only the bare value (money like "10.00", a status code like "409",
an error code like "COUPON_LIMIT", a count like "2").

{checks}"""


class Prediction(BaseModel):
    reasoning: str = Field(description="Short calculation from the rules and seed data")
    value: str = Field(description="Bare predicted value, e.g. '10.00', '409', 'COUPON_LIMIT', '2'")


def _schema(n: int) -> type[BaseModel]:
    """One named field per check (c1, c2, ...) so predictions cannot be misnumbered or skipped."""
    return create_model(f"Predictions{n}", **{f"c{i}": (Prediction, ...) for i in range(1, n + 1)})


def _blind_steps(test: dict) -> tuple[str, str, list[dict]]:
    """Describe the requests and which fields to predict, without expected values."""
    lines, asks, checks = [], [], []
    for n, step in enumerate(test["steps"], 1):
        body = {k: v for k, v in (step.get("body") or {}).items() if v is not None}
        lines.append(f"{n}. {step['method']} {step['path']}{' ' + json.dumps(body) if body else ''}")
        # Success codes (200 vs 201) are not in the requirements; error codes are.
        if (step.get("expect_status") or 0) >= 400:
            checks.append({"step": n, "field": "HTTP status", "op": "equals", "value": str(step["expect_status"])})
            asks.append(f"c{len(checks)}: HTTP status code returned by request {n}")
        for c in step["checks"]:
            if c["op"] not in ("equals", "length"):
                continue  # 'contains'/'not_equals' cannot be predicted as one value
            checks.append({"step": n, **c})
            what = "number of entries in" if c["op"] == "length" else "value of"
            asks.append(f"c{len(checks)}: {what} '{c['field']}' in the response to request {n}")
    return "\n".join(lines), "\n".join(asks), checks


def _same(predicted: str, expected: str) -> bool:
    """Compare loosely: the reviewer may write '400 EMPTY_CART', '$10.00' or '[]'."""
    predicted = predicted.strip()
    if predicted.startswith("["):
        try:
            predicted = str(len(json.loads(predicted)))
        except ValueError:
            pass
    try:
        want = float(expected)
    except ValueError:
        return re.search(rf"\b{re.escape(expected.strip())}\b", predicted, re.I) is not None
    number = re.search(r"-?\d+(?:\.\d+)?", predicted)
    return number is not None and abs(float(number.group()) - want) < 0.005


def _usable(predicted: str, expected: str) -> bool:
    """A numeric expectation needs a numeric prediction; anything else needs some text."""
    predicted = predicted.strip().lower()
    if predicted in ("", "null", "none", "n/a"):
        return False
    try:
        float(expected)
    except ValueError:
        return True
    return re.search(r"\d", predicted) is not None


def review_test(test: dict, spec: str, llm: LLM) -> dict:
    steps, asks, checks = _blind_steps(test)
    if not checks:
        return {"model": llm.model, "verdict": "agree", "issues": [], "checked": 0}
    schema = _schema(len(checks))
    try:
        raw = llm.generate(PROMPT.format(spec=spec, steps=steps, checks=asks), system=SYSTEM, schema=schema,
                           temperature=0, purpose=f"review-{test['id']}")
        predicted = schema.model_validate_json(raw)
    except (LLMError, ValidationError) as exc:
        return {"model": llm.model, "error": str(exc)[:500]}

    issues, skipped = [], 0
    for n, check in enumerate(checks, 1):
        p = getattr(predicted, f"c{n}")
        if not _usable(p.value, check["value"]):
            skipped += 1  # blank or wrong kind of answer: the reviewer has no real opinion
            continue
        if not _same(p.value, check["value"]):
            issues.append(f"step {check['step']} {check['field']}: test expects {check['value']!r}, "
                          f"reviewer predicts {p.value!r} ({p.reasoning})")
    return {"model": llm.model, "verdict": "disagree" if issues else "agree", "issues": issues,
            "checked": len(checks) - skipped, "skipped": skipped}


def review_suite(suite_path: str, llm: LLM | None = None, on_result=None) -> dict:
    """Review every accepted test and store the result next to it in the suite file."""
    path = Path(suite_path)
    suite = json.loads(path.read_text())
    spec = Path(suite["spec"]).read_text()
    llm = llm or LLM(model=DEFAULT_GEMINI_MODEL, cache=is_example(spec))
    for entry in suite["accepted"]:
        entry["review"] = review_test(entry["test"], spec, llm)
        if on_result:
            on_result(entry)
    path.write_text(json.dumps(suite, indent=2, ensure_ascii=False))
    return suite
