"""Render results.json as a self-contained HTML report, uncertain results first."""

import json
from collections import Counter
from html import escape
from pathlib import Path

ORDER = ["BUG", "BAD_TEST", "ENV_ERROR", "PASS"]
LABELS = {"BUG": "Suspected bug", "BAD_TEST": "Bad test (fails on known-good)",
          "ENV_ERROR": "Environment error", "PASS": "Passed"}

CSS = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f5f9;color:#16141f}
main{max-width:980px;margin:0 auto;padding:24px 16px}
h1{margin:0 0 4px} .meta{color:#6b6878;margin-bottom:16px}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.tile{background:#fff;border:1px solid #ebe8f0;border-radius:12px;padding:10px 16px;min-width:120px}
.tile b{font-size:24px;display:block}
.BUG b{color:#b42318} .BAD_TEST b{color:#b54708} .ENV_ERROR b{color:#6941c6} .PASS b{color:#16a34a}
details{background:#fff;border:1px solid #ebe8f0;border-radius:12px;margin:8px 0;padding:10px 14px}
summary{cursor:pointer;font-weight:600} .tag{font-size:12px;padding:1px 8px;border-radius:999px;margin-right:6px}
.tag.BUG{background:#fee4e2;color:#b42318} .tag.BAD_TEST{background:#fef0c7;color:#b54708}
.tag.ENV_ERROR{background:#ebe9fe;color:#6941c6} .tag.PASS{background:#dcfae6;color:#16a34a}
table{border-collapse:collapse;width:100%;margin:8px 0} td,th{border-bottom:1px solid #ebe8f0;padding:4px 6px;text-align:left;vertical-align:top}
.fail{color:#b42318;font-weight:600} pre{background:#f6f5f9;padding:8px;border-radius:8px;overflow:auto;font-size:12px;margin:4px 0}
h2{margin-top:28px}
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


def _raw_steps(run: dict) -> str:
    out = []
    for n, step in enumerate(run["steps"], 1):
        out.append(f"<pre>{n}. {escape(json.dumps(step['request']))}\n→ "
                   f"{escape(json.dumps(step['response'], ensure_ascii=False))[:1500]}</pre>")
    return "".join(out)


def render(run_dir: Path) -> Path:
    data = json.loads((run_dir / "results.json").read_text())
    counts = Counter(r["verdict"] for r in data["results"])
    parts = [f"<h1>Test run {escape(run_dir.name)}</h1>"]
    if data["status"] == "ENV_ERROR":
        parts.append(f"<p class='fail'>Environment failed; no test was judged.</p><pre>{escape(data['env_error'])}</pre>")
    else:
        parts.append(f"<div class='meta'>Target <b>{escape(data['target']['ref'])}</b> @ {escape(data['target']['commit'])}"
                     f" · baseline <b>{escape(data['baseline']['ref'])}</b> @ {escape(data['baseline']['commit'])}"
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
                shown = r["baseline"] if verdict == "BAD_TEST" else r["target"]
                where = "known-good baseline" if verdict == "BAD_TEST" else "target"
                error = f"<p class='fail'>{escape(shown['error'])}</p>" if shown["error"] else ""
                parts.append(
                    f"<details {'open' if verdict == 'BUG' else ''}><summary><span class='tag {verdict}'>{verdict}</span>"
                    f"{escape(t['id'])} · {escape(t['title'])} <small>({escape(t['kind'])})</small></summary>"
                    f"<p>Checks on the {where}:</p>{error}{_checks_table(shown)}"
                    f"<details><summary>Raw requests and responses</summary>{_raw_steps(shown)}</details></details>")
    html = (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Test report {escape(run_dir.name)}</title><style>{CSS}</style></head><body><main>{''.join(parts)}</main></body></html>")
    out = run_dir / "report.html"
    out.write_text(html)
    return out
