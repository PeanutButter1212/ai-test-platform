"""Command line entry point.

    python -m tester generate [--spec PATH] [--rule R1 ...]
    python -m tester review [--suite PATH] [--provider ollama|gemini] [--model NAME]
    python -m tester run [--suite PATH] [--target REF]
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from . import generator, report, review, runner
from .llm import LLM

DEFAULT_SPEC = "specs/shop-requirements.md"
DEFAULT_SUITE = "generated/v2/suite.json"
ICONS = {"PASS": "✅", "BUG": "❌", "BAD_TEST": "🔧", "NEEDS_REVIEW": "🙋", "UNSTABLE": "⚠️ ", "ENV_ERROR": "🔌"}


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


def cmd_review(args):
    def show(entry):
        test, rv = entry["test"], entry["review"]
        if "error" in rv:
            print(f"❔ ERROR     {test['id']:6} {test['title']}\n   {rv['error'][:160]}")
        elif rv["verdict"] == "agree":
            print(f"👍 agree     {test['id']:6} {test['title']}")
        else:
            print(f"🚩 disagree  {test['id']:6} {test['title']}")
            for issue in rv["issues"]:
                print(f"   - {issue}")

    model = args.model or (os.environ.get("REVIEW_MODEL", review.DEFAULT_GEMINI_MODEL) if args.provider == "gemini" else None)
    llm = LLM(model=model, provider=args.provider)
    print(f"Reviewing {args.suite} with {llm.model} ({args.provider})...")
    suite = review.review_suite(args.suite, llm, on_result=show)
    counts = Counter(e["review"].get("verdict", "error") for e in suite["accepted"])
    print(f"\nagree {counts['agree']} · disagree {counts['disagree']} · error {counts['error']}")
    print(f"Saved reviews into {args.suite}")


def cmd_run(args):
    run_dir = runner.run_suite(args.suite, args.target)
    data = json.loads((run_dir / "results.json").read_text())
    if data["status"] == "ENV_ERROR":
        print(f"🔌 Environment failed, no tests judged:\n{data['env_error']}")
    else:
        for r in data["results"]:
            failed = [c for s in r["target"]["steps"] for c in s["checks"] if not c["passed"]]
            detail = f"  → {failed[0]['field']}: expected {failed[0]['expected']}, got {failed[0]['actual']}" if failed else ""
            print(f"{ICONS[r['verdict']]} {r['verdict']:12} {r['test']['id']:6} {r['test']['title']}{detail}")
            if r.get("attempts"):
                print(f"   🔁 {len(r['attempts'])} attempts: {report.attempt_marks(r['attempts'])}")
            if r.get("reason"):
                print(f"   {'🔌 not judged' if r['verdict'] == 'ENV_ERROR' else '🙋 needs a human'}: {r['reason']}")
            for a in r.get("repairs", []):
                changes = "; ".join(report.changed_checks(a["before"], a["after"])) if a.get("after") else ""
                print(f"   🔧 repair {a['attempt']}: {a.get('decision', 'error')} → {a['outcome']}"
                      f"{' (' + changes + ')' if changes else ''}")
            diag = r.get("triage", {}).get("diagnosis")
            if diag and r["verdict"] != "BAD_TEST":
                loc = r["triage"]["location"]
                where = f"{diag['file']}:{loc['line']}" if loc["verified"] else f"{diag['file']} (location unverified)"
                print(f"   🤖 AI: {diag['summary']}\n      at {where} · suggested fix: {diag['suggested_fix'].strip() or '(remove the quoted line)'}")
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

    v = sub.add_parser("review", help="blind second opinion on each test from another model")
    v.add_argument("--suite", default=DEFAULT_SUITE)
    v.add_argument("--provider", choices=["gemini", "ollama"], default="gemini")
    v.add_argument("--model", default=None, help="model name (default: REVIEW_MODEL for gemini, OLLAMA_MODEL for ollama)")
    v.set_defaults(func=cmd_review)

    r = sub.add_parser("run", help="run the suite; an AI judges every failure as bug, bad test or needs review")
    r.add_argument("--suite", default=DEFAULT_SUITE)
    r.add_argument("--target", default=None, help="git ref to test (default: working tree)")
    r.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
