"""v1 (superseded): ask the LLM to write a pytest file directly from the spec.

Kept for comparison with the v2 declarative approach. Usage:
    python -m tester.v1_codegen specs/shop-requirements.md
    BASE_URL=http://localhost:8000 pytest generated/v1
"""

import re
import sys
from pathlib import Path

from .llm import LLM

OUT = Path(__file__).resolve().parent.parent / "generated" / "v1" / "test_generated.py"

SYSTEM = "You are a senior QA engineer who writes precise, runnable API tests."

PROMPT = """Write a pytest test file for the HTTP API described in the requirements below.

- Use httpx. Read the base URL from the BASE_URL environment variable.
- Call POST /api/reset at the start of every test so each test starts from seed data.
- Cover every rule with normal, boundary and error cases.
- Reply with only the Python code.

Requirements:
{spec}
"""


def generate(spec_path: str) -> Path:
    spec = Path(spec_path).read_text()
    code = LLM().generate(PROMPT.format(spec=spec), system=SYSTEM, purpose="v1-codegen")
    # Models often wrap code in a markdown fence despite being told not to.
    match = re.search(r"```(?:python)?\n(.*?)```", code, re.S)
    if match:
        code = match.group(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(code)
    return OUT


if __name__ == "__main__":
    print(generate(sys.argv[1] if len(sys.argv) > 1 else "specs/shop-requirements.md"))
