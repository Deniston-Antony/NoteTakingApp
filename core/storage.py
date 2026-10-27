"""Saves lectures as folders: data/lectures/<id>/lecture.json plus assets/ (images) and media/."""
import base64
import json
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

import markdown as md

from config import CFG
from core.mathfix import fix_obj
from core.notes_generator import fmt_time

LECTURES = CFG.data_dir / "lectures"


def lecture_dir(lid: str) -> Path:
    return LECTURES / lid


def new_lecture(title: str) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "lecture"
    lid = datetime.now().strftime("%Y%m%d-%H%M%S-") + slug
    (lecture_dir(lid) / "assets").mkdir(parents=True, exist_ok=True)
    (lecture_dir(lid) / "media").mkdir(exist_ok=True)
    return {"id": lid, "title": title, "created": datetime.now().isoformat(timespec="seconds"),
            "status": "processing", "sources": {}, "transcript": [], "units": [], "sections": []}


# Background jobs save while the UI reads. On Windows a file can't be replaced while it is
# being read, so saves and reads in this app take turns, and retry if another program
# (antivirus, search indexer) briefly holds the file.
_lock = threading.RLock()


def _retry(fn, tries: int = 20):
    for i in range(tries):
        try:
            return fn()
        except (PermissionError, json.JSONDecodeError):
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def save(lec: dict) -> None:
    path = lecture_dir(lec["id"]) / "lecture.json"
    if not path.parent.exists():
        return  # the lecture was deleted while it was being generated
    tmp = path.with_suffix(".tmp")
    data = json.dumps(lec, ensure_ascii=False, indent=1)
    with _lock:
        _retry(lambda: tmp.write_text(data, encoding="utf-8"))
        _retry(lambda: tmp.replace(path))


def load(lid: str) -> dict | None:
    path = lecture_dir(lid) / "lecture.json"
    if not path.exists():
        return None
    with _lock:
        lec = _retry(lambda: json.loads(path.read_text(encoding="utf-8")))
    # repair maths in notes made before the LaTeX fix existed (Python scripts are left alone)
    lec["sections"] = fix_obj(lec.get("sections", []))
    return lec


def list_lectures() -> list[dict]:
    assign = _read_folders()["assign"]
    known = set(folders())
    out = []
    for d in sorted(LECTURES.iterdir(), reverse=True):
        f = d / "lecture.json"
        if f.exists():
            try:
                lec = load(d.name)
                folder = assign.get(lec["id"])
                out.append({"id": lec["id"], "title": lec["title"], "created": lec["created"],
                            "status": lec.get("status"), "folder": folder if folder in known else None})
            except Exception:
                pass
    return out


def delete(lid: str) -> None:
    shutil.rmtree(lecture_dir(lid), ignore_errors=True)
    move([lid], None)


# ---------- folders ----------
# Kept in data/folders.json (not inside each lecture), so moving a lecture never clashes
# with a background job that is saving that lecture.
FOLDERS_FILE = CFG.data_dir / "folders.json"


def _read_folders() -> dict:
    if not FOLDERS_FILE.exists():
        return {"folders": [], "assign": {}}
    with _lock:
        data = _retry(lambda: json.loads(FOLDERS_FILE.read_text(encoding="utf-8")))
    data.setdefault("folders", [])
    data.setdefault("assign", {})
    return data


def _write_folders(data: dict) -> None:
    tmp = FOLDERS_FILE.with_suffix(".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=1)
    with _lock:
        _retry(lambda: tmp.write_text(text, encoding="utf-8"))
        _retry(lambda: tmp.replace(FOLDERS_FILE))


def folders() -> list[str]:
    return sorted(_read_folders()["folders"], key=str.lower)


def _clean_name(name: str, existing: list[str], allow: str | None = None) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("Please type a folder name.")
    if len(name) > 60:
        raise ValueError("Folder names can be at most 60 characters.")
    if any(f.lower() == name.lower() and f != allow for f in existing):
        raise ValueError(f"A folder called '{name}' already exists.")
    return name


def create_folder(name: str) -> str:
    with _lock:
        data = _read_folders()
        name = _clean_name(name, data["folders"])
        data["folders"].append(name)
        _write_folders(data)
    return name


def rename_folder(old: str, new: str) -> str:
    with _lock:
        data = _read_folders()
        new = _clean_name(new, data["folders"], allow=old)
        data["folders"] = [new if f == old else f for f in data["folders"]]
        data["assign"] = {k: (new if v == old else v) for k, v in data["assign"].items()}
        _write_folders(data)
    return new


def delete_folder(name: str) -> None:
    """Removes the folder. Its lectures are kept and become 'not in a folder'."""
    with _lock:
        data = _read_folders()
        data["folders"] = [f for f in data["folders"] if f != name]
        data["assign"] = {k: v for k, v in data["assign"].items() if v != name}
        _write_folders(data)


def move(lids: list[str], folder: str | None) -> None:
    """Puts lectures into `folder` (None = not in a folder)."""
    with _lock:
        data = _read_folders()
        if folder is not None and folder not in data["folders"]:
            raise ValueError(f"No folder called '{folder}'.")
        for lid in lids:
            if folder is None:
                data["assign"].pop(lid, None)
            else:
                data["assign"][lid] = folder
        _write_folders(data)


def folder_of(lid: str) -> str | None:
    data = _read_folders()
    f = data["assign"].get(lid)
    return f if f in data["folders"] else None


def asset_path(lec: dict, name: str) -> Path:
    return lecture_dir(lec["id"]) / "assets" / name


# ---------- export ----------

def to_markdown(lec: dict, level: str = "long", embed_images: bool = False) -> str:
    def img(name):
        if embed_images:
            data = base64.b64encode(asset_path(lec, name).read_bytes()).decode()
            mime = "png" if name.endswith(".png") else "jpeg"
            return f"data:image/{mime};base64,{data}"
        return f"assets/{name}"

    lines = [f"# {lec['title']}", f"*Created {lec['created']}*", ""]
    for s in lec["sections"]:
        n = s["notes"]
        lines += [f"## {s['title']}", "", f"**In short:** {n['short']}", "", n.get(level) or n["long"], ""]
        for uid in n.get("best_images", []):
            u = lec["units"][uid]
            if u.get("image") and asset_path(lec, u["image"]).exists():
                lines += [f"![{u['label']}]({img(u['image'])})", f"*{u['label']}*", ""]
        if n.get("key_points"):
            lines += ["### Key points"] + [f"- {p}" for p in n["key_points"]] + [""]
        if n.get("key_terms"):
            lines += ["### Key terms"] + [f"- **{t['term']}** — {t['definition']}" for t in n["key_terms"]] + [""]
        if s.get("references"):
            lines += ["### References"] + [f"- [{r['label']}]({r['url']})" if r.get("url") else f"- {r['label']}"
                                          for r in s["references"]] + [""]
        if n.get("further_reading"):
            lines += ["### Further reading (AI-suggested, please check)"] + [f"- {r}" for r in n["further_reading"]] + [""]
        q = s.get("quiz")
        if q:
            lines += ["### Exam questions"]
            for i, m in enumerate(q.get("mcq", []), 1):
                lines.append(f"{i}. {m['question']}")
                lines += [f"   - {'ABCDEF'[j]}) {o}" for j, o in enumerate(m["options"])]
                lines.append(f"   - *Answer: {'ABCDEF'[m['answer_index']]} — {m['explanation']}*")
            for item in q.get("short_answer", []) + q.get("long_answer", []):
                lines += [f"- **Q:** {item['question']}", f"  - *Answer:* {item['answer']}"]
            lines.append("")
        c = s.get("code")
        if c:
            lines += [f"### Python: {c['title']}", c["overview"], "", "```python", c["script"].rstrip(), "```", ""]
    return "\n".join(lines)


def to_html(lec: dict, level: str = "long") -> str:
    body = md.markdown(to_markdown(lec, level, embed_images=True), extensions=["fenced_code", "tables"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{lec['title']}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;line-height:1.6}}
img{{max-width:100%;border:1px solid #ddd}}pre{{background:#f5f5f5;padding:1rem;overflow:auto}}
h2{{border-bottom:2px solid #eee;padding-bottom:.3rem;margin-top:2.5rem}}</style>
</head><body>{body}</body></html>"""
