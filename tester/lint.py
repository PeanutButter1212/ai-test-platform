"""Deterministic checks on generated tests, run before anything executes."""

import re

from .dsl import TestCase

KNOWN_PATHS = [
    r"/api/health", r"/api/reset", r"/api/products", r"/api/carts",
    r"/api/carts/\{\w+\}", r"/api/carts/\{\w+\}/items", r"/api/carts/\{\w+\}/items/\d+",
    r"/api/carts/\{\w+\}/coupons", r"/api/carts/\{\w+\}/coupons/\w+",
    r"/api/carts/\{\w+\}/checkout",
    # literal ids are allowed too (e.g. a cart that does not exist)
    r"/api/carts/\d+(/.*)?",
]


def parse_rule_ids(spec: str) -> set[str]:
    return set(re.findall(r"\*\*(R\d+)\b", spec))


def lint(test: TestCase, rule_ids: set[str]) -> list[str]:
    """Return a list of problems; an empty list means the test may run."""
    problems = []
    if test.rule not in rule_ids:
        problems.append(f"tests unknown rule {test.rule}")
    if not test.steps:
        problems.append("has no steps")

    saved: set[str] = set()
    has_expectation = False
    for n, step in enumerate(test.steps, 1):
        if not any(re.fullmatch(p, step.path) for p in KNOWN_PATHS):
            problems.append(f"step {n}: unknown API path {step.path}")
        for var in re.findall(r"\{(\w+)\}", step.path):
            if var not in saved:
                problems.append(f"step {n}: uses {{{var}}} before it is saved")
        if step.save_id_as:
            saved.add(step.save_id_as)
        if step.expect_status is not None or step.checks:
            has_expectation = True
        for check in step.checks:
            if check.rule not in rule_ids:
                problems.append(f"step {n}: check on '{check.field}' cites unknown rule {check.rule}")
            if not check.why.strip():
                problems.append(f"step {n}: check on '{check.field}' gives no reason")
    if not has_expectation:
        problems.append("never checks anything")
    return problems
