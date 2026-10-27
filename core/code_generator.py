"""Creates a runnable Python script (with a full explanation) for a section of notes."""
import re

from config import CFG
from core import code_runner, llm

SYSTEM = (
    "You are an expert Python teacher. You write small, correct, well-commented Python 3.12 scripts "
    "that help students understand a concept by running code, and you explain code clearly to beginners."
)

CODE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "goal": {"type": "string"},
        "script": {"type": "string"},
        "overview": {"type": "string"},
        "line_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"lines": {"type": "string"}, "explanation": {"type": "string"}},
                "required": ["lines", "explanation"],
            },
        },
        "expected_output": {"type": "string"},
        "try_next": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "goal", "script", "overview", "line_notes", "expected_output", "try_next"],
}

RULES = (
    "Rules for the script:\n"
    "- Self-contained; only the standard library, numpy, pandas, matplotlib, scipy and scikit-learn.\n"
    "- No input(), no internet, no reading files that don't exist; it may write files in the current folder.\n"
    "- Print clearly labelled output. If a chart helps, use matplotlib and call plt.show().\n"
    "- Must finish in under 15 seconds. Use clear names and helpful comments.\n"
)


def _clean(script: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", script, flags=re.S)
    return (m.group(1) if m else script).strip() + "\n"


def _write(section: dict, lecture_title: str, request: str, simple: bool) -> dict:
    notes = section["notes"]
    prompt = (
        f"Lecture: {lecture_title}\nSection: {section['title']}\n\nNOTES\n{notes['medium']}\n\n"
        "Key points:\n" + "\n".join(f"- {p}" for p in notes.get("key_points", [])) + "\n\n"
        "Write a Python script that demonstrates, simulates, calculates or visualises the main concept of "
        "this section so a student can run it and learn from the output. If the topic is not technical, "
        "make a useful study tool for it instead (e.g. a timeline, a data table, a flashcard drill that "
        "prints questions and answers, or a small model of the idea).\n"
        + (f"The student asked for: {request}\n" if request else "")
        + ("Keep it SHORT and SIMPLE (under 60 lines). With numpy, keep every vector and matrix 2-D with "
           "explicit shapes (e.g. column vectors of shape (n, 1)) and check shapes before using @.\n"
           if simple else "")
        + RULES +
        "Then explain the code completely: overview (Markdown: what it does, how it connects to the "
        "concept, how it works step by step), line_notes (cover every part of the script in order; "
        "'lines' is a line range like '1-6'), expected_output (what the student will see), and try_next "
        "(3 small changes the student can try)."
    )
    data = llm.chat_json(prompt, CODE_SCHEMA, system=SYSTEM, temperature=0.2)
    data["script"] = _clean(data.get("script", ""))
    return data


def generate_code(section: dict, lecture_title: str, request: str = "", run_name: str = "check") -> dict:
    data = check_and_fix(_write(section, lecture_title, request, simple=False), run_name)
    if data["verified"]:
        return data
    # fixing didn't work: start again with a simpler script
    retry = check_and_fix(_write(section, lecture_title, request, simple=True), run_name, attempts=1)
    if retry["verified"]:
        retry["fix_log"] = data["fix_log"] + ["Wrote a new, simpler script."] + retry["fix_log"]
        return retry
    return data


FIX_SCHEMA = {
    "type": "object",
    "properties": {"script": {"type": "string"}, "what_changed": {"type": "string"}},
    "required": ["script", "what_changed"],
}


def check_and_fix(data: dict, run_name: str, attempts: int | None = None) -> dict:
    """Runs the script; if it crashes, asks the model to fix it (a few tries).
    Every try sees the earlier failed tries, so the model doesn't undo its own fixes."""
    attempts = CFG.code_fix_attempts if attempts is None else attempts
    data["fix_log"] = []
    history = []  # [what was changed, error it still gave]
    for _ in range(attempts + 1):
        result = code_runner.run_script(data["script"], run_name)
        data["verified"] = result["returncode"] == 0
        if data["verified"]:
            break
        error = result["stderr"][-2000:] or result["stdout"][-1000:]
        if history:
            history[-1][1] = error
        if len(data["fix_log"]) >= attempts:
            break
        tried = ""
        for change, err in history:
            last_line = err.strip().splitlines()[-1] if err.strip() else "?"
            tried += f"\n- Tried: {change}\n  Still failed with: {last_line}"
        prompt = (f"This script fails.\n\nSCRIPT\n```python\n{data['script']}```\n\nERROR\n{error}\n\n"
                  + (f"Earlier fix attempts that did NOT work (do not repeat them):{tried}\n\n" if history else "")
                  + "Find the real cause (check array shapes, types and names carefully) and fix it.\n"
                  + RULES + "Return the full fixed script and one sentence on what you changed.")
        fix = None
        # first try with step-by-step reasoning; if that answer breaks, try a normal answer
        for think in (True, False):
            try:
                fix = llm.chat_json(prompt, FIX_SCHEMA, system=SYSTEM, temperature=0.1, think=think,
                                    max_tokens=5000 if think else None)
                break
            except llm.LLMError:
                continue
        if fix is None:
            break
        data["script"] = _clean(fix.get("script", data["script"]))
        data["fix_log"].append(fix.get("what_changed", ""))
        history.append([fix.get("what_changed", ""), ""])
    if data["fix_log"]:
        data["overview"] += ("\n\n> ⚠️ The script was changed automatically to fix errors, so the "
                             "line-by-line notes may not match exactly.")
    return data


def explain_code(script: str) -> dict:
    """Explains a script the student edited themselves."""
    schema = {k: CODE_SCHEMA["properties"][k] for k in ("overview", "line_notes", "expected_output")}
    return llm.chat_json(
        f"Explain this Python script completely for a student.\n```python\n{script}```\n"
        "Give overview (Markdown), line_notes covering every part in order ('lines' like '1-6'), "
        "and expected_output.",
        {"type": "object", "properties": schema, "required": list(schema)}, system=SYSTEM, temperature=0.2)
