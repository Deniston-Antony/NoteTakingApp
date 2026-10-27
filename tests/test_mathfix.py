"""Checks the LaTeX repair on damaged text like the AI produces, and scans saved lectures.
Run:  venv\\Scripts\\python.exe tests\\test_mathfix.py"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.mathfix import fix_obj, fix_text  # noqa: E402

# what the Jacobian looked like after the damage (control characters where backslashes were)
broken = ("$ g(x) = [g_1(x), g_2(x), \text{...}, g_m(x)]^T $ and the Jacobian is: "
          "$$ G_x = \begin{bmatrix} \frac{\text{d}g_1}{\text{d}x_1} & \frac{\text{d}g_1}{\text{d}x_n} \\ "
          "\frac{\text{d}g_m}{\text{d}x_1} & \frac{\text{d}g_m}{\text{d}x_n} \\ \right] $$")
# the same with single backslashes turned into control chars, as JSON would do
broken = (broken.replace("\\text", "\text").replace("\\begin", "\x08egin").replace("\\frac", "\x0crac")
          .replace("\\right", "\right").replace(" \\\\ ", " \\ "))
fixed = fix_text(broken)
print("BROKEN:", repr(broken[:120]))
print("FIXED: ", fixed)
assert "\\begin{bmatrix}" in fixed and "\\end{bmatrix}" in fixed
assert "\\frac{\\text{d}g_1}" in fixed and "\x0c" not in fixed and "\x08" not in fixed and "\t" not in fixed
assert fixed.count("\\\\") == 2, fixed
assert "\\cdots" in fixed

# things that must NOT change
same = ["Line one\nThe next line\n- bullet", "Normal text with $\\alpha + \\beta$ and $$\\frac{a}{b}$$",
        "Already fine: $$\\begin{bmatrix} 1 & 2 \\\\ 3 & 4 \\end{bmatrix}$$", "tab\tseparated\tvalues"]
for s in same:
    assert fix_text(s) == s, (s, fix_text(s))
code = {"script": "def f():\n\ttext = 'a\\nb'\n\treturn text", "overview": "Uses \x0crac"}
out = fix_obj(code)
assert out["script"] == code["script"] and out["overview"] == "Uses \\frac"
assert fix_text(r"$$ g(x) \\_approx g(\mu) + G (x - \mu) $$") == r"$$ g(x) \approx g(\mu) + G (x - \mu) $$"
assert fix_text(r"$$\begin{bmatrix} a \\ b \end{bmatrix}$$") == r"$$\begin{bmatrix} a \\ b \end{bmatrix}$$"
print("unit checks OK")

# scan saved lectures: how many damaged spots get repaired
total = 0
for f in glob.glob(str(Path(__file__).resolve().parents[1] / "data/lectures/*/lecture.json")):
    secs = json.load(open(f, encoding="utf-8"))["sections"]
    before = json.dumps(secs)
    after = json.dumps(fix_obj(secs))
    n = sum(before.count(c) for c in ("\\b", "\\f", "\\t", "\\r")) - sum(after.count(c) for c in ("\\b", "\\f", "\\t", "\\r"))
    if before != after:
        total += 1
print(f"saved lectures with maths that gets repaired: {total}")
