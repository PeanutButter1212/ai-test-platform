"""AI diagnosis of failed tests: likely cause, location and a suggested fix.

The diagnosis is advice for a developer, never applied automatically. The one
claim we can check in code, that the quoted lines exist in the named file,
is verified here; anything else is labelled as an unverified AI suggestion.
"""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .llm import LLM, LLMError

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILES = ["shop/pricing.py", "shop/app.py", "shop/db.py"]

SYSTEM = """You are a senior engineer diagnosing a failing API test.
Use only the evidence given. Quote code exactly as it appears in the source.
If the evidence suggests the test itself is wrong rather than the code, say so."""

PROMPT = """A test failed. Diagnose the most likely cause in the source code.

Rule under test:
{rule_text}

Test: {test_id} - {title}

Failed checks (expected vs actual):
{failed}

Requests and responses of the failing run:
{steps}

Source code (line numbers added for reference, not part of the code):
{source}"""


class Diagnosis(BaseModel):
    summary: str = Field(description="One sentence: what is wrong")
    culprit: Literal["code", "test", "unclear"] = Field(description="Is the app code or the test wrong?")
    file: str = Field(description="Path of the file containing the defect, e.g. 'shop/pricing.py'")
    function: str = Field(description="Function containing the defect")
    quoted_code: str = Field(description="The faulty line(s), copied exactly from the source without line numbers")
    suggested_fix: str = Field(description="Replacement code for the quoted lines")
    explanation: str = Field(description="Why this code produces the observed result")
    confidence: Literal["high", "medium", "low"]


def _source_listing(root: Path) -> str:
    parts = []
    for rel in SOURCE_FILES:
        lines = (root / rel).read_text().splitlines()
        numbered = "\n".join(f"{n:4} | {line}" for n, line in enumerate(lines, 1))
        parts.append(f"### {rel}\n{numbered}")
    return "\n\n".join(parts)


def _rule_text(spec: str, rule: str) -> str:
    match = re.search(rf"^- \*\*{rule}\b.*$", spec, re.M)
    return match.group(0) if match else rule


def locate(diagnosis: Diagnosis, root: Path) -> dict:
    """Deterministically check the quoted code exists in the named file."""
    path = root / diagnosis.file
    if not path.is_file():
        return {"verified": False, "reason": f"file {diagnosis.file} does not exist"}
    # Compare with all whitespace removed: models often re-wrap multi-line statements.
    quoted = re.sub(r"\s+", "", diagnosis.quoted_code)
    if not quoted:
        return {"verified": False, "reason": "no code quoted"}
    flat, line_of = [], []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        for ch in re.sub(r"\s+", "", line):
            flat.append(ch)
            line_of.append(n)
    pos = "".join(flat).find(quoted)
    if pos == -1:
        return {"verified": False, "reason": "quoted code not found in file"}
    return {"verified": True, "line": line_of[pos], "end_line": line_of[pos + len(quoted) - 1]}


def diagnose(result: dict, spec: str, root: Path = ROOT, llm: LLM | None = None) -> dict:
    """Return a diagnosis record for one failed test result, or an error record."""
    test, run = result["test"], result["target"]
    failed = [f"- {c['field']} {c['op']} {c['expected']!r}, actual {c['actual']!r} (rule {c['rule']})"
              for s in run["steps"] for c in s["checks"] if not c["passed"]]
    steps = "\n".join(
        f"{n}. {s['request']['method']} {s['request']['path']} {json.dumps(s['request']['body'])}"
        f" -> {s['response']['status']} {json.dumps(s['response']['body'])[:600]}"
        for n, s in enumerate(run["steps"], 1))
    prompt = PROMPT.format(rule_text=_rule_text(spec, test["rule"]), test_id=test["id"], title=test["title"],
                           failed="\n".join(failed) or run.get("error") or "(none)", steps=steps,
                           source=_source_listing(root))
    try:
        llm = llm or LLM()
        raw = llm.generate(prompt, system=SYSTEM, schema=Diagnosis, purpose=f"triage-{test['id']}")
        diagnosis = Diagnosis.model_validate_json(raw)
    except (LLMError, ValidationError) as exc:
        return {"error": str(exc)[:500]}
    return {"diagnosis": diagnosis.model_dump(), "location": locate(diagnosis, root)}
