"""Command line entry point.

    python -m tester generate [--spec PATH] [--rule R1 ...]
    python -m tester run [--suite PATH] [--target REF] [--baseline REF]
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from . import generator, report, runner

DEFAULT_SPEC = "specs/shop-requirements.md"
DEFAULT_SUITE = "generated/v2/suite.json"
ICONS = {"PASS": "✅", "BUG": "❌", "BAD_TEST": "⚠️ ", "ENV_ERROR": "🔌"}


def cmd_generate(args):
    suite = generator.generate(args.spec, args.rule)
    path = generator.save(suite, Path(args.out))
    print(f"Generated with {suite['model']}: {len(suite['accepted'])} accepted, "
          f"{len(suite['rejected'])} rejected by linter")
    for r in suite["rejected"]:
        print(f"  ✗ {r['test']['id']}: {'; '.join(r['lint'])}")
    for f in suite["generation_failures"]:
        print(f"  ! {f['rule']}: generation failed: {f['error'][:120]}")
    print(f"Saved {path}")


def cmd_run(args):
    run_dir = runner.run_suite(args.suite, args.target, args.baseline)
    data = json.loads((run_dir / "results.json").read_text())
    if data["status"] == "ENV_ERROR":
        print(f"🔌 Environment failed, no tests judged:\n{data['env_error']}")
    else:
        for r in data["results"]:
            failed = [c for s in r["target" if r["verdict"] != "BAD_TEST" else "baseline"]["steps"]
                      for c in s["checks"] if not c["passed"]]
            detail = f"  → {failed[0]['field']}: expected {failed[0]['expected']}, got {failed[0]['actual']}" if failed else ""
            print(f"{ICONS[r['verdict']]} {r['verdict']:9} {r['test']['id']:6} {r['test']['title']}{detail}")
        counts = Counter(r["verdict"] for r in data["results"])
        print("\n" + " · ".join(f"{v} {counts.get(v, 0)}" for v in ICONS))
    print(f"Report: {report.render(run_dir)}")


def main():
    parser = argparse.ArgumentParser(prog="tester")
    sub = parser.add_subparsers(required=True)

    g = sub.add_parser("generate", help="generate tests from the requirements with the LLM")
    g.add_argument("--spec", default=DEFAULT_SPEC)
    g.add_argument("--rule", action="append", help="only this rule (repeatable)")
    g.add_argument("--out", default=DEFAULT_SUITE)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="run the suite on the target and the known-good baseline")
    r.add_argument("--suite", default=DEFAULT_SUITE)
    r.add_argument("--target", default=None, help="git ref to test (default: working tree)")
    r.add_argument("--baseline", default="shop-clean", help="known-good git ref")
    r.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
