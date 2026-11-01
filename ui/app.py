"""Streamlit front end: requirements in plain language -> reviewed, approved tests -> run.

    streamlit run ui/app.py

Every AI step uses the same modules as the CLI, so results, raw logs and the
LLM cache are shared. Verdicts are still decided by code, never by the AI.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tester import generator, report, requirements, review, runner  # noqa: E402
from tester.llm import LOG_PATH, LLM, LLMError  # noqa: E402

ICONS = {"PASS": "✅", "BUG": "❌", "BAD_TEST": "🔧", "NEEDS_REVIEW": "🙋", "UNSTABLE": "⚠️", "ENV_ERROR": "🔌"}

st.set_page_config(page_title="AI Test Platform", page_icon="🧪", layout="wide")
state = st.session_state
state.setdefault("messages", [])
state.setdefault("rules", [])
state.setdefault("questions", [])
state.setdefault("ai_calls", {})


def reset_from(step: str):
    """Changing an earlier step invalidates everything after it."""
    order = ["suite", "approved", "run_dir"]
    for key in order[order.index(step):]:
        state.pop(key, None)


def work_dir() -> Path:
    if "work_dir" not in state:
        state.work_dir = ROOT / "runs" / "ui" / datetime.now().strftime("%Y%m%d-%H%M%S")
        state.work_dir.mkdir(parents=True)
    return state.work_dir


def log_offset() -> int:
    return LOG_PATH.stat().st_size if LOG_PATH.exists() else 0


def count_calls(step: str, offset: int):
    """Count the AI calls a step made since `offset` in the raw call log, by source (live/cache/failed)."""
    with LOG_PATH.open() as f:
        f.seek(offset)
        sources = [json.loads(line).get("source") for line in f if line.strip()]
    state.ai_calls[step] = {src: sources.count(src) for src in ("live", "cache", "failed") if src in sources}


def ai_note(step: str):
    calls = state.ai_calls.get(step)
    if calls:
        st.caption("AI calls · " + " · ".join(f"{n} {'cached' if src == 'cache' else src}" for src, n in calls.items()))


def describe(test: dict) -> str:
    lines = []
    for n, s in enumerate(test["steps"], 1):
        body = {k: v for k, v in (s.get("body") or {}).items() if v is not None}
        expect = f" → expect {s['expect_status']}" if s.get("expect_status") else ""
        lines.append(f"{n}. `{s['method']} {s['path']}` {json.dumps(body) if body else ''}{expect}")
        for c in s["checks"]:
            lines.append(f"    - `{c['field']}` {c['op']} **{c['value']}** — {c['why']} ({c['rule']})")
    return "\n".join(lines)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🧪 AI Test Platform")
    st.caption("Requirements in, executable tests out. AI writes, reviews and judges; code runs every check; "
               "a human gets anything the AI is unsure about.")
    st.markdown(f"**Writes tests:** `{LLM().model}`  \n**Reviews tests:** `{review.DEFAULT_GEMINI_MODEL}`  \n"
                f"**Target:** working tree")
    if st.button("Load example requirements", width="stretch"):
        state.messages = [{"role": "assistant", "content": "Loaded the example shop requirements (R1–R7)."}]
        state.rules, state.questions = requirements.example_rules(), []
        reset_from("suite")
        st.rerun()
    if st.button("Start over", width="stretch"):
        for key in list(state.keys()):
            del state[key]
        st.rerun()

# ---------------------------------------------------------------- 1. requirements
st.header("1 · Describe the requirements")
st.caption("Type the business rules in your own words. The AI rewrites them as numbered, testable rules "
           "and asks about anything a test would need that you did not say.")

for m in state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("e.g. Orders of $100 or more get 10% off. Only one coupon per cart."):
    state.messages.append({"role": "user", "content": prompt})
    offset = log_offset()
    with st.spinner("Structuring requirements…"):
        try:
            result = requirements.structure(state.messages)
        except (LLMError, ValueError) as exc:
            state.messages.append({"role": "assistant", "content": f"⚠️ AI call failed: {exc}"})
        else:
            state.rules = [r.model_dump() for r in result.rules]
            state.questions = result.questions
            reply = f"I have {len(state.rules)} rule(s) so far — see the table below."
            if result.questions:
                reply += "\n\nBefore I write tests, please clarify:\n" + "\n".join(f"- {q}" for q in result.questions)
            else:
                reply += " Nothing is unclear; you can generate tests."
            state.messages.append({"role": "assistant", "content": reply})
    count_calls("requirements", offset)
    reset_from("suite")
    st.rerun()

if state.rules:
    st.subheader("Rules")
    st.caption("Edit any cell directly. These rules, plus the shop's seed data and API, are what the AI tests against.")
    edited = st.data_editor(pd.DataFrame(state.rules), num_rows="dynamic", width="stretch",
                            hide_index=True, key=f"rules_{len(state.messages)}",
                            column_config={"id": st.column_config.TextColumn("ID", width="small"),
                                           "title": st.column_config.TextColumn("Title", width="medium"),
                                           "text": st.column_config.TextColumn("Rule", width="large")})
    # New rows added in the editor start empty (NaN); keep only complete rules.
    rules = [r for r in edited.to_dict("records") if isinstance(r.get("id"), str) and isinstance(r.get("text"), str)]
    if rules != state.rules:
        state.rules = rules
        reset_from("suite")
    ai_note("requirements")
    if state.questions:
        st.info("The AI still has open questions above. Answer them in the chat, or generate anyway.")

# ---------------------------------------------------------------- 2. generate
if state.rules:
    st.header("2 · Generate tests")
    if st.button("Generate tests with AI", type="primary"):
        spec_path = work_dir() / "spec.md"
        spec_path.write_text(requirements.compose(state.rules))
        offset = log_offset()
        suite = {"spec": str(spec_path), "model": None, "accepted": [], "rejected": [], "generation_failures": []}
        progress = st.progress(0.0, text="Generating…")
        for n, rule in enumerate(state.rules, 1):
            progress.progress((n - 1) / len(state.rules), text=f"Generating tests for {rule['id']}…")
            part = generator.generate(str(spec_path), [rule["id"]])
            suite["model"] = part["model"]
            for key in ("accepted", "rejected", "generation_failures"):
                suite[key] += part[key]
        progress.empty()
        count_calls("generate", offset)
        generator.save(suite, work_dir() / "suite.json")
        reset_from("approved")
        state.suite = suite

    if "suite" in state:
        suite = state.suite
        c1, c2, c3 = st.columns(3)
        c1.metric("Tests written", len(suite["accepted"]) + len(suite["rejected"]))
        c2.metric("Passed the linter", len(suite["accepted"]))
        c3.metric("Rejected by linter", len(suite["rejected"]))
        ai_note("generate")
        for r in suite["rejected"]:
            st.warning(f"Linter rejected **{r['test']['id']}**: {'; '.join(r['lint'])}")
        for f in suite["generation_failures"]:
            st.error(f"Generation failed for {f['rule']}: {f['error'][:200]}")

# ---------------------------------------------------------------- 3. review + approve
if "suite" in state and state.suite["accepted"]:
    st.header("3 · AI review")
    st.caption("A second model predicts every expected value without seeing the test's answer. "
               "Mismatches are flagged and left out, unless you choose to approve tests yourself.")
    suite = state.suite
    manual = st.toggle("Let me approve tests myself", value=False, on_change=reset_from, args=("approved",))
    if st.button("Run AI review"):
        llm = LLM(model=review.DEFAULT_GEMINI_MODEL)
        spec = Path(suite["spec"]).read_text()
        offset = log_offset()
        progress = st.progress(0.0)
        for n, entry in enumerate(suite["accepted"], 1):
            progress.progress((n - 1) / len(suite["accepted"]), text=f"Reviewing {entry['test']['id']}…")
            entry["review"] = review.review_test(entry["test"], spec, llm)
        progress.empty()
        count_calls("review", offset)
        generator.save(suite, work_dir() / "suite.json")
        reset_from("approved")
    ai_note("review")

    def approve(keep: set[str], by: str):
        approved = {**suite, "accepted": [e for e in suite["accepted"] if e["test"]["id"] in keep],
                    "rejected": suite["rejected"] + [{**e, "lint": [f"left out by {by}"]}
                                                     for e in suite["accepted"] if e["test"]["id"] not in keep],
                    "approved_by": by, "approved_at": datetime.now().isoformat(timespec="seconds")}
        state.approved = str(generator.save(approved, work_dir() / "approved.json"))
        state.pop("run_dir", None)

    reviewed = all("review" in e for e in suite["accepted"])
    flagged = [e for e in suite["accepted"] if e.get("review", {}).get("verdict") == "disagree"]
    rows = []
    for e in suite["accepted"]:
        rv = e.get("review", {})
        verdict = rv.get("verdict", "error" if "error" in rv else "not reviewed")
        rows.append({"keep": verdict != "disagree", "id": e["test"]["id"], "kind": e["test"]["kind"],
                     "title": e["test"]["title"],
                     "review": {"agree": "👍 agree", "disagree": "🚩 disagree"}.get(verdict, f"❔ {verdict}")})

    if manual:
        table = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch",
                               disabled=["id", "kind", "title", "review"], key="approve_table",
                               column_config={"keep": st.column_config.CheckboxColumn("Keep?")})
        keep = set(table.loc[table["keep"], "id"])
        if st.button(f"Approve {len(keep)} of {len(rows)} tests", type="primary", disabled=not keep):
            approve(keep, "human")
    else:
        st.dataframe(pd.DataFrame(rows).drop(columns="keep"), hide_index=True, width="stretch")
        if reviewed and "approved" not in state:
            approve({r["id"] for r in rows if r["keep"]}, "AI review")

    for e in flagged:
        st.error(f"🚩 **{e['test']['id']}** — reviewer disagrees, {'untick to leave out' if manual else 'left out'}:\n"
                 + "\n".join(f"- {i}" for i in e["review"]["issues"]))
    with st.expander("See every test"):
        for e in suite["accepted"]:
            st.markdown(f"**{e['test']['id']}** · {e['test']['kind']} · {e['test']['title']}")
            st.markdown(describe(e["test"]))

# ---------------------------------------------------------------- 4. run
if "approved" in state:
    st.header("4 · Run against the shop")
    st.caption("Every test runs on a fresh copy of the shop; code decides pass or fail. For each failure the AI reads "
               "the requirements and the shop's code: code wrong = BUG, test wrong = BAD_TEST (the AI repairs it), "
               "unsure = NEEDS_REVIEW. A failing test is rerun twice first; if the reruns disagree it is UNSTABLE.")
    if st.button("Run tests", type="primary"):
        offset = log_offset()
        with st.spinner("Starting the shop, running every test and judging failures…"):
            state.run_dir = str(runner.run_suite(state.approved))
        count_calls("run", offset)  # AI judge and test repairs

    if "run_dir" in state:
        run_dir = Path(state.run_dir)
        data = json.loads((run_dir / "results.json").read_text())
        if data["status"] == "ENV_ERROR":
            st.error(f"🔌 The environment failed, so no test was judged:\n\n{data['env_error']}")
        else:
            results = data["results"]
            cols = st.columns(len(ICONS))
            for col, verdict in zip(cols, ICONS):
                col.metric(f"{ICONS[verdict]} {verdict}", sum(r["verdict"] == verdict for r in results))
            ai_note("run")
            for r in results:
                if r["verdict"] != "BUG":
                    continue
                failed = [c for s in r["target"]["steps"] for c in s["checks"] if not c["passed"]]
                with st.container(border=True):
                    st.markdown(f"❌ **{r['test']['id']}** {r['test']['title']}")
                    for c in failed:
                        st.markdown(f"- `{c['field']}`: expected **{c['expected']}**, got **{c['actual']}** ({c['rule']})")
                    diag = r.get("triage", {}).get("diagnosis")
                    if diag:
                        loc = r["triage"]["location"]
                        where = f"{diag['file']}:{loc['line']} (location verified)" if loc["verified"] \
                            else f"{diag['file']} (location not verified)"
                        st.markdown(f"🤖 **AI suggestion — advice only, needs developer review**  \n"
                                    f"{diag['summary']}  \nat `{where}`")
                        st.code(diag["suggested_fix"] or "(remove the quoted line)", language="python")
            for r in results:
                if r["verdict"] == "UNSTABLE":
                    st.warning(f"⚠️ **{r['test']['id']}** {r['test']['title']}: gave different results when rerun "
                               f"({report.attempt_marks(r['attempts'])}), so it was not judged. A human should look.")
                if r["verdict"] == "NEEDS_REVIEW":
                    st.warning(f"🙋 **{r['test']['id']}** {r['test']['title']}: needs a human, {r['reason']}.")
                for a in r.get("repairs", []):
                    changes = report.changed_checks(a["before"], a["after"]) if a.get("after") else []
                    st.info(f"🔧 **{r['test']['id']}**: the AI judged its own test wrong and repaired it "
                            f"(attempt {a['attempt']}: {a['outcome']}).  \n{a.get('diagnosis') or a.get('error', '')}"
                            + "".join(f"  \n`{c}`" for c in changes))
            st.dataframe(pd.DataFrame([{"verdict": f"{ICONS[r['verdict']]} {r['verdict']}", "id": r["test"]["id"],
                                        "title": r["test"]["title"]} for r in results]),
                         hide_index=True, width="stretch")
        with st.expander("Full report (also saved to disk)"):
            path = report.render(run_dir)
            st.caption(str(path))
            st.iframe(path, height=800)  # report.py escapes all AI and response text
