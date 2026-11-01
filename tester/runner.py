"""Run a suite against the target and the known-good baseline, then classify each test.

Verdicts (decided by code, never by the LLM):
  PASS       passes on baseline and target
  BUG        passes on baseline, fails on target  -> suspected defect in the target
  BAD_TEST   fails on the known-good baseline     -> the test itself is wrong
  ENV_ERROR  a request could not be completed     -> no conclusion about app or test
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


def classify(baseline: dict, target: dict) -> str:
    if baseline["error"] or target["error"]:
        return "ENV_ERROR"
    if not baseline["passed"]:
        return "BAD_TEST"
    return "PASS" if target["passed"] else "BUG"


def _run_all(tests, ref, run_dir, label, repair_with=None):
    """Run every test on one shop instance. With repair_with (the spec), tests that fail
    here are sent back to the AI and re-run on this same instance."""
    repairs = {}
    with shop_instance(ref) as env:
        results = {t.id: run_test(t, env["base_url"]) for t in tests}
        if repair_with:
            llm = LLM()
            for i, test in enumerate(tests):
                r = results[test.id]
                if not r["passed"] and not r["error"]:
                    tests[i], results[test.id], repairs[test.id] = repair_test(
                        test, r, repair_with, env["base_url"], llm)
        shutil.copy(env["log"], run_dir / f"server-{label}.log")
        return {"ref": env["ref"], "commit": env["commit"]}, results, repairs


def run_suite(suite_path: str, target_ref: str | None = None, baseline_ref: str = "shop-clean",
              triage: bool = True, repair: bool = True) -> Path:
    suite = json.loads(Path(suite_path).read_text())
    tests = [TestCase.model_validate(e["test"]) for e in suite["accepted"]]
    run_dir = RUNS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)

    record = {"suite": suite_path, "started": datetime.now().isoformat(timespec="seconds"),
              "tests": len(tests), "status": "complete", "results": []}
    spec = Path(suite["spec"]).read_text()
    try:
        # Baseline first: wrong tests are found (and repaired) before the target is judged.
        record["baseline"], base_results, repairs = _run_all(tests, baseline_ref, run_dir, "baseline",
                                                             repair_with=spec if repair else None)
        record["target"], target_results, _ = _run_all(tests, target_ref, run_dir, "target")
    except EnvError as exc:
        # The environment never became healthy: report that, and judge no test.
        record["status"] = "ENV_ERROR"
        record["env_error"] = str(exc)
    else:
        for test in tests:
            b, t = base_results[test.id], target_results[test.id]
            result = {"test": test.model_dump(), "verdict": classify(b, t), "baseline": b, "target": t}
            if test.id in repairs:
                result["repairs"] = repairs[test.id]
            record["results"].append(result)
        if triage:
            # Diagnose suspected bugs against the source that was actually tested.
            source_root = ROOT if target_ref is None else None
            for r in record["results"]:
                if r["verdict"] == "BUG" and source_root:
                    r["triage"] = diagnose(r, spec, source_root)

    (run_dir / "results.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return run_dir
