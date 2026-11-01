"""Run a suite against the shop and decide, for every failing test, who is at fault.

Code decides pass/fail for every check. For each failing test an AI judge reads the
requirements, the failed checks and the source code, and blames the code, the test,
or neither:

  PASS          every check passed
  BUG           AI blames the code, and the code it quotes really is in that file
  BAD_TEST      AI blames the test; the AI rewrites it and the rewrite passes
  NEEDS_REVIEW  AI is unsure, quotes code that is not there, or cannot repair the test
  ENV_ERROR     a request could not be completed -> no conclusion about app or test
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
                if r["error"]:
                    verdict, details = "ENV_ERROR", {}
                elif r["passed"]:
                    verdict, details = "PASS", {}
                else:
                    verdict, test, r, details = judge_failure(test, r, spec, env, llm)
                record["results"].append({"test": test.model_dump(), "verdict": verdict, "target": r, **details})
            shutil.copy(env["log"], run_dir / "server.log")
    except EnvError as exc:
        # The environment never became healthy: report that, and judge no test.
        record.update(status="ENV_ERROR", env_error=str(exc), results=[])

    (run_dir / "results.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return run_dir
