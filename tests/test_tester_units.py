"""Unit tests for the deterministic parts of the tester (no LLM, no server)."""

from pathlib import Path

from tester.dsl import Check, TestCase
from tester.engine import MISSING, evaluate, resolve
from tester.lint import lint
from tester.report import changed_checks
from tester.requirements import EXAMPLE_SPEC, compose, example_rules
from tester.review import _blind_steps, _same, _usable
from tester import runner
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


def test_judge_failure_maps_ai_verdicts(monkeypatch):
    test = TestCase(id="R1-01", rule="R1", kind="normal", title="t", steps=[])
    failing = {"passed": False, "error": None, "steps": []}
    env = {"workdir": ".", "base_url": "http://shop"}

    def judge(culprit, verified=True, repaired=True):
        triage = {"diagnosis": {"culprit": culprit, "explanation": "why"}, "location": {"verified": verified}}
        monkeypatch.setattr(runner, "diagnose", lambda *a: triage)
        monkeypatch.setattr(runner, "repair_test", lambda t, r, *a, **k: (t, {**r, "passed": repaired}, []))
        return runner.judge_failure(test, failing, "spec", env, llm=None)[0]

    assert judge("code") == "BUG"
    assert judge("code", verified=False) == "NEEDS_REVIEW"   # quoted code is not in the file
    assert judge("test") == "BAD_TEST"                       # repaired test now passes
    assert judge("test", repaired=False) == "NEEDS_REVIEW"
    assert judge("unclear") == "NEEDS_REVIEW"


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


def test_review_is_blind():
    test = TestCase(id="R1-01", rule="R1", kind="normal", title="t", steps=[
        {"method": "POST", "path": "/api/carts/{cart}/coupons", "body": {"code": "X"}, "expect_status": 404,
         "checks": [Check(field="detail.code", op="equals", value="COUPON_NOT_FOUND", rule="R5",
                          why="unknown codes fail with COUPON_NOT_FOUND")]}]).model_dump()
    steps, asks, checks = _blind_steps(test)
    assert "COUPON_NOT_FOUND" not in steps + asks and "404" not in steps + asks
    assert [c["value"] for c in checks] == ["404", "COUPON_NOT_FOUND"]


def test_review_comparison():
    assert _same("$10.00", "10.00") and _same("422 QTY_RANGE", "422") and _same("[]", "0")
    assert _same("400 EMPTY_CART", "EMPTY_CART") and not _same("OUT_OF_STOCK", "EMPTY_CART")
    assert not _same("9.00", "10.00")
    assert not _usable("", "422") and not _usable("COUPON_LIMIT", "5.00") and _usable("5.00", "5.00")


def test_example_rules_rebuild_the_example_spec():
    # The UI composes specs from rules; unchanged rules must reproduce the file exactly (and hit the LLM cache).
    assert compose(example_rules()) == EXAMPLE_SPEC.read_text()


def test_changed_checks_lists_only_edited_expectations():
    before = {"steps": [{"checks": [{"field": "total", "value": "90.00"}, {"field": "subtotal", "value": "100.00"}]}]}
    after = {"steps": [{"checks": [{"field": "total", "value": "90.00"}, {"field": "subtotal", "value": "99.00"}]}]}
    assert changed_checks(before, after) == ["step 1 subtotal: 100.00 → 99.00"]
