"""Runs Python scripts from the Python Lab and collects printed output and charts.

Scripts run in a separate Python process with a time limit, inside their own folder.
This is NOT a full sandbox: only run scripts you trust."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

from config import CFG

# Runs before the user's script: makes plt.show() save charts as PNG files instead of opening windows.
BOOT = r'''
import os, sys, runpy
os.environ["MPLBACKEND"] = "Agg"
_save = None
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
    _n = [0]
    def _save(*a, **k):
        for num in _plt.get_fignums():
            _n[0] += 1
            _plt.figure(num).savefig(f"figure_{_n[0]:02d}.png", dpi=110, bbox_inches="tight")
        _plt.close("all")
    _plt.show = _save
except ImportError:
    pass
sys.argv = ["script.py"]
try:
    runpy.run_path("script.py", run_name="__main__")
finally:
    if _save:
        _save()
'''


def run_script(code: str, run_name: str, stdin_text: str = "", timeout: int | None = None) -> dict:
    run_dir = CFG.data_dir / "runs" / run_name
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    (run_dir / "script.py").write_text(code, encoding="utf-8")
    (run_dir / "_boot.py").write_text(BOOT, encoding="utf-8")
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg"}

    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run([sys.executable, "-X", "utf8", "_boot.py"], cwd=run_dir, input=stdin_text,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout or CFG.code_timeout, env=env)
        stdout, stderr, code_ = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = f"Stopped: the script ran longer than {timeout or CFG.code_timeout} seconds."
        code_ = -1

    # hide the helper's own lines from tracebacks
    stderr = "\n".join(l for l in stderr.splitlines()
                       if "_boot.py" not in l and "runpy" not in l and "run_path(" not in l
                       and "_run_module_code" not in l and "_run_code" not in l and "exec(code, run_globals)" not in l)

    figures = sorted(str(p) for p in run_dir.glob("figure_*.png"))
    files = sorted(str(p) for p in run_dir.iterdir()
                   if p.name not in ("script.py", "_boot.py") and not p.name.startswith("figure_") and p.is_file())
    return {"stdout": stdout, "stderr": stderr.strip(), "returncode": code_, "timed_out": timed_out,
            "figures": figures, "files": files, "seconds": round(time.time() - t0, 2)}
