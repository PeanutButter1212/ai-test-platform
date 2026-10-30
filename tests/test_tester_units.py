"""Unit tests for the deterministic parts of the tester (no LLM, no server)."""

from pathlib import Path

from tester.dsl import Check, TestCase
from tester.engine import MISSING, evaluate, resolve
from tester.lint import lint
from tester.runner import classify
from tester.triage import Diagnosis, locate

RULES = {"R1", "R2"}


def make_test(**overrides):
    data = {"id": "R1-01", "rule": "R1", "kind": "normal", "title": "t", "steps": [
        {"method": "POST", "path": "/api/carts", "save_id_as": "cart", "expect_status": 201}]}
    data.update(overrides)
    return TestCase.model_validate(data)


def test_resolve_paths():
    data = {"detail": {"code": "X"}, "items": [{"qty": 2}]}
    assert resolve(data, "detail.code") == "X"
    assert resolve(data, "items.0.qty") == 2
    assert resolve([{"id": 5, "stock": 3}], "[id=5].stock") == 3
    assert resolve(data, "items.3.qty") is MISSING
    assert resolve(data, "nope") is MISSING


def test_evaluate_ops():
    check = Check(field="total", op="equals", value="10.00", rule="R1", why="w")
    assert evaluate(check, {"total": "10.00"}) == (True, "10.00")
    assert evaluate(check, {"total": "9.00"}) == (False, "9.00")
    contains = Check(field="coupons", op="contains", value="SAVE10", rule="R1", why="w")
    assert evaluate(contains, {"coupons": ["SAVE10"]})[0]
    length = Check(field="items", op="length", value="2", rule="R1", why="w")
    assert evaluate(length, {"items": [1, 2]})[0]


def test_lint_accepts_valid_test():
    assert lint(make_test(), RULES) == []


def test_lint_rejects_problems():
    bad = make_test(rule="R9", steps=[{"method": "GET", "path": "/api/carts/{cart}/nope"}])
    problems = lint(bad, RULES)
    assert any("unknown rule R9" in p for p in problems)
    assert any("unknown API path" in p for p in problems)
    assert any("before it is saved" in p for p in problems)
    assert any("never checks anything" in p for p in problems)


def test_classify():
    ok, fail = {"passed": True, "error": None}, {"passed": False, "error": None}
    err = {"passed": False, "error": "ConnectError"}
    assert classify(ok, ok) == "PASS"
    assert classify(ok, fail) == "BUG"
    assert classify(fail, fail) == "BAD_TEST"
    assert classify(fail, ok) == "BAD_TEST"
    assert classify(ok, err) == "ENV_ERROR"


def test_locate_verifies_quotes(tmp_path):
    src = tmp_path / "shop"
    src.mkdir()
    (src / "a.py").write_text("x = 1\nresult = call(\n    a,\n    b)\n")

    def diag(quote):
        return Diagnosis(summary="s", culprit="code", file="shop/a.py", function="f",
                         quoted_code=quote, suggested_fix="", explanation="", confidence="low")

    assert locate(diag("result = call(a, b)"), tmp_path) == {"verified": True, "line": 2, "end_line": 4}
    assert locate(diag("y = 2"), tmp_path)["verified"] is False
    assert locate(diag("x = 1"), Path("/nonexistent"))["verified"] is False
