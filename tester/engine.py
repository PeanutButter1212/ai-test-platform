"""Executes a TestCase against a running shop. No AI involved: pass/fail is decided here."""

import re
import time

import httpx

from .dsl import Check, TestCase

MISSING = object()


def resolve(data, path: str):
    """Follow a path like 'detail.code', 'items.0.qty' or '[id=5].stock' into JSON data."""
    for part in re.findall(r"\[[^\]]+\]|[^.\[\]]+", path):
        if part.startswith("["):
            key, _, want = part[1:-1].partition("=")
            if not isinstance(data, list):
                return MISSING
            data = next((x for x in data if isinstance(x, dict) and str(x.get(key)) == want), MISSING)
        elif isinstance(data, list) and part.isdigit():
            data = data[int(part)] if int(part) < len(data) else MISSING
        elif isinstance(data, dict):
            data = data.get(part, MISSING)
        else:
            return MISSING
        if data is MISSING:
            return MISSING
    return data


def as_text(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def evaluate(check: Check, data) -> tuple[bool, str]:
    actual = resolve(data, check.field)
    if actual is MISSING:
        return False, "<missing>"
    if check.op == "equals":
        return as_text(actual) == check.value, as_text(actual)
    if check.op == "not_equals":
        return as_text(actual) != check.value, as_text(actual)
    if check.op == "contains":
        items = actual if isinstance(actual, list) else [actual]
        return check.value in [as_text(x) for x in items] or check.value in as_text(actual), as_text(actual)
    if check.op == "length":
        return isinstance(actual, (list, str)) and str(len(actual)) == check.value, (
            str(len(actual)) if isinstance(actual, (list, str)) else as_text(actual))
    return False, f"unknown op {check.op}"


def run_test(test: TestCase, base_url: str) -> dict:
    """Run one test from seed data. Returns a raw, JSON-serialisable record."""
    record = {"test_id": test.id, "steps": [], "passed": True, "error": None}
    started = time.time()
    try:
        with httpx.Client(base_url=base_url, timeout=10) as client:
            client.post("/api/reset").raise_for_status()
            saved: dict[str, str] = {}
            for step in test.steps:
                path = step.path.format(**saved)
                body = step.body.model_dump(exclude_none=True) if step.body else None
                res = client.request(step.method, path, json=body)
                try:
                    data = res.json()
                except ValueError:
                    data = res.text
                if step.save_id_as and isinstance(data, dict) and "id" in data:
                    saved[step.save_id_as] = str(data["id"])

                outcomes = []
                if step.expect_status is not None:
                    ok = res.status_code == step.expect_status
                    outcomes.append({"field": "<status>", "op": "equals", "expected": str(step.expect_status),
                                     "actual": str(res.status_code), "passed": ok, "rule": None, "why": None})
                for check in step.checks:
                    ok, actual = evaluate(check, data)
                    outcomes.append({"field": check.field, "op": check.op, "expected": check.value,
                                     "actual": actual, "passed": ok, "rule": check.rule, "why": check.why})
                record["steps"].append({
                    "request": {"method": step.method, "path": path, "body": body},
                    "response": {"status": res.status_code, "body": data},
                    "checks": outcomes,
                })
                if not all(o["passed"] for o in outcomes):
                    record["passed"] = False
    except (httpx.TransportError, httpx.HTTPStatusError, KeyError) as exc:
        record["passed"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["duration_s"] = round(time.time() - started, 3)
    return record
