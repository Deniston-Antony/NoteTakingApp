"""Checks every UI page renders without errors (uses saved lectures in data/).
Run:  venv\\Scripts\\python.exe tests\\test_ui.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import storage  # noqa: E402

APP = str(ROOT / "NoteTakingApp.py")


def check(at, name):
    errs = [e.value for e in at.exception]
    print(f"{'FAIL' if errs else 'ok  '} {name}")
    for e in errs:
        print("   ", e)
    return not errs


ok = True
at = AppTest.from_file(APP, default_timeout=60).run()
ok &= check(at, "new lecture page")
for kind in ("record", "audio", "youtube", "video"):
    at.radio[0].set_value(kind).run()
    ok &= check(at, f"new page with source={kind}")

for lec in storage.list_lectures():
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["view"] = lec["id"]
    at.run()
    ok &= check(at, f"lecture page: {lec['title']} ({lec['status']})")
    full = storage.load(lec["id"])
    if full and full["sections"]:
        # switch to every section
        for i in range(len(full["sections"])):
            at.radio(key=f"sec_{lec['id']}").set_value(i).run()
            ok &= check(at, f"   section {i + 1}")

print("\nALL OK" if ok else "\nSOME CHECKS FAILED")
