"""Render results.json as a self-contained HTML report, uncertain results first."""

import json
from collections import Counter
from html import escape
from pathlib import Path

ORDER = ["BUG", "NEEDS_REVIEW", "UNSTABLE", "BAD_TEST", "ENV_ERROR", "PASS"]
LABELS = {"BUG": "Bug in the code", "NEEDS_REVIEW": "Needs human review", "BAD_TEST": "Wrong test, repaired by AI",
          "UNSTABLE": "Unstable (reruns disagreed)",
          "ENV_ERROR": "Environment error", "PASS": "Passed"}

CSS = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f5f9;color:#16141f}
main{max-width:980px;margin:0 auto;padding:24px 16px}
h1{margin:0 0 4px} .meta{color:#6b6878;margin-bottom:16px}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.tile{background:#fff;border:1px solid #ebe8f0;border-radius:12px;padding:10px 16px;min-width:120px}
.tile b{font-size:24px;display:block}
.BUG b{color:#b42318} .NEEDS_REVIEW b{color:#b54708} .UNSTABLE b{color:#c4320a} .BAD_TEST b{color:#175cd3} .ENV_ERROR b{color:#6941c6} .PASS b{color:#16a34a}
details{background:#fff;border:1px solid #ebe8f0;border-radius:12px;margin:8px 0;padding:10px 14px}
summary{cursor:pointer;font-weight:600} .tag{font-size:12px;padding:1px 8px;border-radius:999px;margin-right:6px}
.tag.BUG{background:#fee4e2;color:#b42318} .tag.NEEDS_REVIEW{background:#fef0c7;color:#b54708}
.tag.BAD_TEST{background:#d1e9ff;color:#175cd3} .tag.UNSTABLE{background:#ffead5;color:#c4320a}
.tag.ENV_ERROR{background:#ebe9fe;color:#6941c6} .tag.PASS{background:#dcfae6;color:#16a34a}
table{border-collapse:collapse;width:100%;margin:8px 0} td,th{border-bottom:1px solid #ebe8f0;padding:4px 6px;text-align:left;vertical-align:top}
.fail{color:#b42318;font-weight:600} pre{background:#f6f5f9;padding:8px;border-radius:8px;overflow:auto;font-size:12px;margin:4px 0}
h2{margin-top:28px} .ai{background:#f4f3ff;border:1px solid #d9d6fe;border-radius:10px;padding:8px 12px;margin:10px 0}
.ai p{margin:4px 0} .ok{color:#16a34a;font-size:12px} .fail{font-size:12px}
"""


def _checks_table(run: dict) -> str:
    rows = []
    for n, step in enumerate(run["steps"], 1):
        req = step["request"]
        for c in step["checks"]:
            cls = "" if c["passed"] else "fail"
            rows.append(
                f"<tr class='{cls}'><td>{n}. {escape(req['method'])} {escape(req['path'])}</td>"
                f"<td>{escape(c['field'])} {escape(c['op'])}</td><td>{escape(c['expected'])}</td>"
                f"<td>{escape(c['actual'])}</td><td>{escape(c['rule'] or '')}</td>"
                f"<td>{escape(c['why'] or '')}</td></tr>")
    head = "<tr><th>Step</th><th>Check</th><th>Expected</th><th>Actual</th><th>Rule</th><th>Why</th></tr>"
    return f"<table>{head}{''.join(rows)}</table>"


def _triage(t: dict | None) -> str:
    if not t:
        return ""
    if "error" in t:
        return f"<div class='ai'><b>🤖 AI diagnosis failed:</b> {escape(t['error'][:300])}</div>"
    d, loc = t["diagnosis"], t["location"]
    where = (f"{escape(d['file'])}:{loc['line']} <span class='ok'>✓ location verified in source</span>"
             if loc["verified"] else
             f"{escape(d['file'])} <span class='fail'>✗ location not verified ({escape(loc['reason'])})</span>")
    fix = escape(d["suggested_fix"].strip()) or "(remove the quoted line)"
    return (f"<div class='ai'><b>🤖 AI suggestion</b> <small>({escape(d['confidence'])} confidence, "
            f"blames the {escape(d['culprit'])}; advice only, needs developer review)</small>"
            f"<p>{escape(d['summary'])}</p><p>Where: {where} in <code>{escape(d['function'])}</code></p>"
            f"<p>Current code:</p><pre>{escape(d['quoted_code'].strip())}</pre>"
            f"<p>Suggested fix:</p><pre>{fix}</pre><p>{escape(d['explanation'])}</p></div>")


def _raw_steps(run: dict) -> str:
    out = []
    for n, step in enumerate(run["steps"], 1):
        out.append(f"<pre>{n}. {escape(json.dumps(step['request']))}\n→ "
                   f"{escape(json.dumps(step['response'], ensure_ascii=False))[:1500]}</pre>")
    return "".join(out)


def attempt_marks(attempts: list[dict]) -> str:
    """e.g. '❌ ✅ ❌' for fail, pass, fail."""
    return " ".join("🔌" if a["error"] else "✅" if a["passed"] else "❌" for a in attempts)


def _attempts(attempts: list | None) -> str:
    if not attempts:
        return ""
    rows = "".join(
        f"<details><summary>Attempt {n}: {attempt_marks([a])}</summary>{_checks_table(a)}{_raw_steps(a)}</details>"
        for n, a in enumerate(attempts, 1))
    return f"<p>Ran {len(attempts)} times: {attempt_marks(attempts)}</p>{rows}"


def changed_checks(before: dict, after: dict) -> list[str]:
    """Expectations the AI changed while repairing a test, e.g. 'step 2 tier_discount: 0.00 → 10.00'."""
    def values(test):
        return {(n, c["field"]): c["value"] for n, s in enumerate(test["steps"], 1) for c in s["checks"]}
    old, new = values(before), values(after)
    return [f"step {n} {field}: {old.get((n, field), '—')} → {new.get((n, field), '—')}"
            for n, field in sorted(old.keys() | new.keys()) if old.get((n, field)) != new.get((n, field))]


def _repairs(history: list | None) -> str:
    if not history:
        return ""
    rows = "".join(
        f"<li>Attempt {a['attempt']}: <b>{escape(a.get('decision', 'error'))}</b> → {escape(a['outcome'])}"
        f"<br>{escape(a.get('diagnosis') or a.get('error', ''))}"
        + "".join(f"<br><code>{escape(c)}</code>" for c in
                  (changed_checks(a["before"], a["after"]) if a.get("after") else []))
        + "</li>" for a in history)
    return (f"<div class='ai'><b>🔧 The AI judged its own test wrong and repaired it</b>"
            f"<ol>{rows}</ol><small>The original test failed; the checks below are for the repaired test.</small></div>")


def render(run_dir: Path) -> Path:
    data = json.loads((run_dir / "results.json").read_text())
    counts = Counter(r["verdict"] for r in data["results"])
    parts = [f"<h1>Test run {escape(run_dir.name)}</h1>"]
    if data["status"] == "ENV_ERROR":
        parts.append(f"<p class='fail'>Environment failed; no test was judged.</p><pre>{escape(data['env_error'])}</pre>")
    else:
        parts.append(f"<div class='meta'>Target <b>{escape(data['target']['ref'])}</b> @ {escape(data['target']['commit'])}"
                     f" · {data['tests']} tests · suite {escape(data['suite'])}</div>")
        parts.append("<div class='tiles'>" + "".join(
            f"<div class='tile {v}'><b>{counts.get(v, 0)}</b>{LABELS[v]}</div>" for v in ORDER) + "</div>")
        for verdict in ORDER:
            group = [r for r in data["results"] if r["verdict"] == verdict]
            if not group:
                continue
            parts.append(f"<h2>{LABELS[verdict]} ({len(group)})</h2>")
            for r in group:
                t = r["test"]
                shown = r["target"]
                label = "🔌 Not judged" if verdict == "ENV_ERROR" else "🙋 Needs a human"
                reason = f"<p class='fail'>{label}: {escape(r['reason'])}</p>" if r.get("reason") else ""
                error = f"<p class='fail'>{escape(shown['error'])}</p>" if shown["error"] else ""
                parts.append(
                    f"<details {'open' if verdict in ('BUG', 'NEEDS_REVIEW', 'UNSTABLE') else ''}><summary><span class='tag {verdict}'>{verdict}</span>"
                    f"{escape(t['id'])} · {escape(t['title'])} <small>({escape(t['kind'])})</small></summary>"
                    f"{reason}{_attempts(r.get('attempts'))}{_repairs(r.get('repairs'))}"
                    f"<p>Checks:</p>{error}{_checks_table(shown)}{_triage(r.get('triage'))}"
                    f"<details><summary>Raw requests and responses</summary>{_raw_steps(shown)}</details></details>")
    html = (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Test report {escape(run_dir.name)}</title><style>{CSS}</style></head><body><main>{''.join(parts)}</main></body></html>")
    out = run_dir / "report.html"
    out.write_text(html)
    return out
