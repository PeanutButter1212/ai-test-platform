"""Turn requirements typed in plain language into numbered, testable rules.

The LLM rewrites what the user said as precise rules (R1, R2, ...) and asks
clarifying questions where a value a test would need is missing or ambiguous.
It must not invent behaviour: unclear points become questions, not rules.
The rules are then combined with the fixed description of the system under
test (seed data and API) to form the spec that test generation reads.
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .llm import LLM

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SPEC = ROOT / "specs" / "shop-requirements.md"

HEADER = """# Shop requirements

Input for the AI test platform. Each rule has an ID that generated tests must cite.

## Business rules

"""
RULE_LINE = re.compile(r"^- \*\*(R\d+) (.+?)\.\*\* (.*)$", re.M)

SYSTEM = """You are a QA analyst. You turn business requirements described in plain language
into precise, testable rules. Keep the user's meaning. Only write rules for what the user
described; never add rules about other features. Ask as few questions as possible, in plain
words a shop owner would understand."""

PROMPT = """The system under test is described below (seed data and API). Use it to word the
rules precisely, e.g. which response field a discount appears in.

{context}

Conversation with the user so far:
{conversation}

Rewrite what the user has asked for as numbered rules R1, R2, ... in the order given. Each rule
needs a short title and one or two precise sentences (exact thresholds, amounts, and the error
for failures if the user gave one). Only cover features the user mentioned.

Questions: ask at most 2, only about features the user mentioned, and only when the answer would
change the value a test expects (for example, does exactly $100 count?). If a reasonable reading
is clear from the user's words and the system description, use it and do not ask. Never ask
about field names, endpoints or implementation. Never ask about something already answered.
If nothing important is unclear, ask nothing."""


class Rule(BaseModel):
    id: str = Field(description="R1, R2, ...")
    title: str = Field(description="2-4 words, e.g. 'Spend discount'")
    text: str = Field(description="The precise, testable rule")


class Structured(BaseModel):
    rules: list[Rule]
    questions: list[str] = Field(description="Clarifying questions; empty if nothing is unclear")


def system_context() -> str:
    """Everything in the example spec after the business rules: seed data and API."""
    spec = EXAMPLE_SPEC.read_text()
    return spec[spec.index("## Seed data"):]


def is_example(spec: str) -> bool:
    """Only the example requirements reuse saved AI answers; anything typed is always live."""
    return spec == EXAMPLE_SPEC.read_text()


def example_rules() -> list[dict]:
    return [{"id": i, "title": t, "text": x} for i, t, x in RULE_LINE.findall(EXAMPLE_SPEC.read_text())]


def compose(rules: list[dict]) -> str:
    """Build a spec in the same format as the example, so unchanged rules reproduce it exactly."""
    lines = [f"- **{r['id']} {r['title'].strip().rstrip('.')}.** {r['text'].strip()}" for r in rules]
    return HEADER + "\n".join(lines) + "\n\n" + system_context()


def structure(messages: list[dict], llm: LLM | None = None) -> Structured:
    """messages: [{"role": "user" | "assistant", "content": str}, ...]"""
    conversation = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    raw = (llm or LLM()).generate(PROMPT.format(context=system_context(), conversation=conversation),
                                  system=SYSTEM, schema=Structured, purpose="structure-requirements")
    return Structured.model_validate_json(raw)
