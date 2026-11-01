"""Run a suite against the shop and decide, for every failing test, who is at fault.

Code decides pass/fail for every check. For each failing test an AI judge reads the
requirements, the failed checks and the source code, and blames the code, the test,
or neither:

  PASS          every check passed
  BUG           AI blames the code, and the code it quotes really is in that file
  BAD_TEST      AI blames the test; the AI rewrites it and the rewrite passes
  NEEDS_REVIEW  AI is unsure, quotes code that is not there, or cannot repair the test
  UNSTABLE      reruns of a failing test gave different results -> not judged, a human should look
  ENV_ERROR     a request could not be completed, or the server said it was unavailable
                (502/503/504) -> no conclusion about app or test

A failing test is rerun RERUNS more times before anything is judged. A pass on a
rerun never turns a failure into PASS: mixed results are UNSTABLE.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from .dsl import TestCase
from .engine import run_test
from .env import EnvError, shop_instance
from .llm import LLM
from .repair import repair_test
from .triage import diagnose

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
RERUNS = 2


def outcome(record: dict):
    """What a run showed: 'pass', the error, or exactly which checks failed with which values."""
    if record["error"]:
        return ("error", record["error"])
    if record["passed"]:
        return "pass"
    return tuple((n, c["field"], c["expected"], c["actual"])
                 for n, s in enumerate(record["steps"], 1) for c in s["checks"] if not c["passed"])


def is_unstable(attempts: list[dict]) -> bool:
    return len({outcome(a) for a in attempts}) > 1


UNAVAILABLE = {"502", "503", "504"}


def server_unavailable(record: dict) -> bool:
    """True if the only thing that failed is the server saying it is temporarily unavailable."""
    failed = [c for s in record["steps"] for c in s["checks"] if not c["passed"]]
    return bool(failed) and all(c["field"] == "<status>" and c["actual"] in UNAVAILABLE for c in failed)


def judge_failure(test: TestCase, record: dict, spec: str, env: dict, llm: LLM) -> tuple[str, TestCase, dict, dict]:
    """AI judge for one failing test. Returns (verdict, final test, final record, details)."""
    details = {"triage": diagnose({"test": test.model_dump(), "target": record}, spec, Path(env["workdir"]), llm)}
    diag, location = details["triage"].get("diagnosis"), details["triage"].get("location", {})
    if diag is None:
        return "NEEDS_REVIEW", test, record, {**details, "reason": "the AI judge failed"}
    if diag["culprit"] == "code":
        if location.get("verified"):
            return "BUG", test, record, details
        return "NEEDS_REVIEW", test, record, {**details, "reason": "the AI blamed code that is not in the file"}
    if diag["culprit"] == "test":
        fixed, fixed_record, history = repair_test(test, record, spec, env["base_url"], llm,
                                                   diagnosis=diag["explanation"])
        details["repairs"] = history
        if fixed_record["passed"]:
            return "BAD_TEST", fixed, fixed_record, details
        return "NEEDS_REVIEW", test, record, {**details, "reason": "the AI blamed the test but could not fix it"}
    return "NEEDS_REVIEW", test, record, {**details, "reason": "the AI is not sure whether the code or the test is wrong"}


def run_suite(suite_path: str, target_ref: str | None = None) -> Path:
    suite = json.loads(Path(suite_path).read_text())
    tests = [TestCase.model_validate(e["test"]) for e in suite["accepted"]]
    spec = Path(suite["spec"]).read_text()
    run_dir = RUNS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)

    record = {"suite": suite_path, "started": datetime.now().isoformat(timespec="seconds"),
              "tests": len(tests), "status": "complete", "results": []}
    try:
        with shop_instance(target_ref) as env:
            record["target"] = {"ref": env["ref"], "commit": env["commit"]}
            llm = LLM()
            for test in tests:
                r = run_test(test, env["base_url"])
                details = {}
                if not r["passed"]:
                    # Never trust a single failure: repeat it, and keep every attempt.
                    attempts = [r] + [run_test(test, env["base_url"]) for _ in range(RERUNS)]
                    details["attempts"] = attempts
                if r["passed"]:
                    verdict = "PASS"
                elif is_unstable(details["attempts"]):
                    verdict = "UNSTABLE"
                elif r["error"]:
                    verdict = "ENV_ERROR"
                elif server_unavailable(r):
                    verdict = "ENV_ERROR"
                    details["reason"] = "the server said it was temporarily unavailable, so nothing was judged"
                else:
                    verdict, test, r, judged = judge_failure(test, r, spec, env, llm)
                    details.update(judged)
                record["results"].append({"test": test.model_dump(), "verdict": verdict, "target": r, **details})
            shutil.copy(env["log"], run_dir / "server.log")
    except EnvError as exc:
        # The environment never became healthy: report that, and judge no test.
        record.update(status="ENV_ERROR", env_error=str(exc), results=[])

    (run_dir / "results.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return run_dir
