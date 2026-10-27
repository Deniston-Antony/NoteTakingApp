r"""Repairs maths (LaTeX) that was damaged on its way out of the AI model.

The model returns its answer as JSON. In JSON, a backslash followed by b, f, n, r or t is a
special character (backspace, form feed, newline, return, tab). So when the model writes the
LaTeX command \frac with one backslash, it arrives as <form feed> + "rac"; \begin becomes
<backspace> + "egin", \text becomes <tab> + "ext", \right becomes <return> + "ight".
Matrix row breaks (\\) also lose one backslash. This module puts them back.
"""
import re

# LaTeX commands that start with a JSON escape letter (only these can be damaged this way)
_T_CMDS = ["textbf", "textit", "textrm", "textstyle", "text", "thicksim", "thickapprox", "therefore", "triangleq", "theta", "tau", "times", "tilde", "tfrac",
           "tanh", "tan", "triangle", "top", "to", "tag", "tbinom"]
_N_CMDS = ["nabla", "neq", "newline", "nonumber", "notin", "nolimits", "nexists", "nu"]
_R_CMDS = ["rightleftharpoons", "rightharpoonup", "rightarrow", "right", "rho", "rangle", "rceil", "rfloor", "rbrace", "rvert", "rVert", "rm"]


def _cmd_regex(ch: str, names: list[str]) -> re.Pattern:
    # the escape swallowed the first letter: "\text" arrives as <tab> + "ext"
    rests = sorted((n[1:] for n in names), key=len, reverse=True)
    return re.compile(re.escape(ch) + "(" + "|".join(rests) + r")(?![A-Za-z])")


_T_RE = _cmd_regex("\t", _T_CMDS)
_N_RE = _cmd_regex("\n", _N_CMDS)
_R_RE = _cmd_regex("\r", _R_CMDS)
_MATRIX_ENVS = r"(?:[pbBvV]?matrix|smallmatrix|cases|aligned|align\*?|array|split|gathered)"
_ENV_RE = re.compile(r"(\\begin\{(" + _MATRIX_ENVS + r")\})(.*?)(\\end\{\2\}|\\right[\]\)\|]|(?=\$\$)|$)", re.S)


def _fix_env(m: re.Match) -> str:
    begin, env, body, end = m.group(1), m.group(2), m.group(3), m.group(4)
    # a lone "\" followed by a space or line break inside a matrix was a row break "\\"
    body = re.sub(r"(?<!\\)\\(?=\s)", r"\\\\", body)
    # \begin{bmatrix} ... \right]  ->  \begin{bmatrix} ... \end{bmatrix}
    if not end.startswith("\\end"):
        end = "\\end{" + env + "}"
    return begin + body + end


_MATH_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.S)
_BAD_CMDS = {r"\bigint": r"\int"}  # commands the model invents that LaTeX doesn't have


def _fix_math(m: re.Match) -> str:
    # inside maths a tab/return followed by letters is always a damaged command (\textstyle, \rho, …)
    t = re.sub(r"\t(?=[A-Za-z])", r"\\t", m.group(0))
    t = re.sub(r"\r(?=[A-Za-z])", r"\\r", t)
    if not t.startswith("$$"):  # inline maths never contains real line breaks
        t = re.sub(r"\n(?=[A-Za-z])", r"\\n", t)
    if "\\begin{" not in t:  # outside matrices "\\approx" / "\\_approx" is an over-escaped "\approx"
        t = re.sub(r"\\\\_?(?=[A-Za-z]{2,})", lambda _: "\\", t)
    for bad, good in _BAD_CMDS.items():
        t = re.sub(re.escape(bad) + r"(?![A-Za-z])", lambda _: good, t)
    return t


def fix_text(s: str) -> str:
    if not s or "\\" not in s and not any(c in s for c in "\x08\x0c\t\r"):
        return s
    s = s.replace("\x08", "\\b").replace("\x0c", "\\f")   # never meant as real characters
    s = _R_RE.sub(lambda m: "\\r" + m.group(1), s)
    s = _T_RE.sub(lambda m: "\\t" + m.group(1), s)
    s = _N_RE.sub(lambda m: "\\n" + m.group(1), s)
    if "$" in s:
        s = _MATH_RE.sub(_fix_math, s)
    if "\\begin{" in s:
        s = _ENV_RE.sub(_fix_env, s)
    # tidy: "\text{...}" used as an ellipsis
    s = re.sub(r"\\text\{\s*\.\.\.\s*\}", r"\\cdots", s)
    s = re.sub(r"\\text\{\s*\.\.\.,\s*\}", r"\\cdots,", s)
    return s


def fix_obj(obj, skip_keys=("script",)):
    """Fixes every string in a dict/list, except fields holding Python code."""
    if isinstance(obj, str):
        return fix_text(obj)
    if isinstance(obj, list):
        return [fix_obj(v, skip_keys) for v in obj]
    if isinstance(obj, dict):
        return {k: (v if k in skip_keys else fix_obj(v, skip_keys)) for k, v in obj.items()}
    return obj
