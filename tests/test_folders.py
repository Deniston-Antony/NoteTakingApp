"""Tests folders: create / rename / delete / move, and the UI for them.
Uses a temporary copy of folders.json, so your real folders are not changed.
Run:  venv\\Scripts\\python.exe tests\\test_folders.py"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import storage  # noqa: E402

real = storage.FOLDERS_FILE
backup = real.with_suffix(".testbackup")
if real.exists():
    shutil.copy(real, backup)
try:
    real.unlink(missing_ok=True)
    lecs = storage.list_lectures()
    assert len(lecs) >= 2, "needs at least 2 saved lectures"
    a, b = lecs[0]["id"], lecs[1]["id"]

    # ---- storage ----
    assert storage.folders() == []
    storage.create_folder("  Robotics  ")
    storage.create_folder("Maths")
    assert storage.folders() == ["Maths", "Robotics"]
    for bad in ("", "   ", "robotics", "x" * 61):
        try:
            storage.create_folder(bad)
            raise AssertionError(f"should refuse {bad!r}")
        except ValueError:
            pass
    storage.move([a, b], "Robotics")
    assert storage.folder_of(a) == "Robotics"
    assert {l["id"]: l["folder"] for l in storage.list_lectures()}[b] == "Robotics"
    storage.rename_folder("Robotics", "Mobile Robotics")
    assert storage.folder_of(a) == "Mobile Robotics"
    storage.move([b], "Maths")
    storage.move([a], None)
    assert storage.folder_of(a) is None and storage.folder_of(b) == "Maths"
    storage.delete_folder("Maths")
    assert storage.folder_of(b) is None and storage.folders() == ["Mobile Robotics"]
    # the lecture itself is untouched by folder changes
    assert storage.load(b) is not None
    print("storage checks OK")

    # ---- UI ----
    storage.move([a], "Mobile Robotics")
    at = AppTest.from_file(str(ROOT / "NoteTakingApp.py"), default_timeout=60)
    at.session_state["view"] = a
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [e.label for e in at.expander]
    assert any("Mobile Robotics" in x for x in labels), labels
    box = at.selectbox(key=f"folder_{a}")
    assert box.value == "Mobile Robotics", box.value
    box.set_value("— Not in a folder —").run()
    assert not at.exception, [e.value for e in at.exception]
    assert storage.folder_of(a) is None
    # create a folder from the lecture page
    at.selectbox(key=f"folder_{a}").set_value("➕ New folder…").run()
    at.text_input(key=f"newf_{a}").input("Week 8").run()
    at.button(key=f"newf_btn_{a}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert storage.folder_of(a) == "Week 8", storage.folder_of(a)
    # bulk move from the sidebar
    at.multiselect(key="move_pick").set_value([a, b]).run()
    at.selectbox(key="move_dest").set_value("Mobile Robotics").run()
    next(x for x in at.button if x.label == "Move").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert storage.folder_of(a) == storage.folder_of(b) == "Mobile Robotics"
    # search
    at.text_input(key="lib_search").input("zzz-no-match").run()
    assert not at.exception
    print("UI checks OK")
finally:
    real.unlink(missing_ok=True)
    if backup.exists():
        shutil.move(backup, real)
print("ALL OK")
