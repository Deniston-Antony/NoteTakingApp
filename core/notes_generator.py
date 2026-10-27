"""Turns lecture "units" (slides and/or pieces of transcript) into sections of notes."""
from typing import Callable

from config import CFG
from core import llm

SYSTEM = (
    "You are an expert university teaching assistant who writes clear, accurate study notes. "
    "Base the notes on the lecture material provided; you may add well-established background "
    "knowledge to explain things, but never invent facts about the lecture. "
    "Write in Markdown. Use LaTeX between $...$ (inline) or $$...$$ (block) for maths. "
    "Put each $$...$$ block on its own line. Use \\begin{bmatrix} ... \\end{bmatrix} for matrices, "
    "with & between columns and \\\\ between rows."
)


def fmt_time(sec: float | None) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def unit_text(u: dict, limit: int | None = None) -> str:
    parts = [f"### {u['label']}"]
    if u.get("slide_text"):
        parts.append("Slide text:\n" + u["slide_text"])
    if u.get("image_desc"):
        parts.append("What the image shows:\n" + u["image_desc"])
    if u.get("speech"):
        when = f" ({fmt_time(u.get('start'))}–{fmt_time(u.get('end'))})" if u.get("start") is not None else ""
        parts.append(f"Lecturer said{when}:\n" + u["speech"])
    text = "\n".join(parts)
    return text if limit is None or len(text) <= limit else text[:limit] + " …"


# ---------- 1. split the lecture into sections ----------

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "start_unit": {"type": "integer"}},
                "required": ["title", "start_unit"],
            },
        }
    },
    "required": ["sections"],
}


def make_outline(units: list[dict], lecture_title: str) -> list[dict]:
    """Returns [{"title", "unit_ids"}] covering every given unit in order.
    `units` can be any run of consecutive units (e.g. the unfinished part of a lecture)."""
    n = len(units)
    ids = [u["id"] for u in units]
    if n <= 2:
        return [{"title": lecture_title or "Lecture notes", "unit_ids": ids}]
    per_unit = max(120, 16000 // n)
    listing = "\n\n".join(f"[U{i}] " + unit_text(u, per_unit) for i, u in enumerate(units))
    max_sections = min(12, max(2, n // 2))
    prompt = (
        f"Lecture: {lecture_title}\n\nBelow are the parts of the lecture in order, labelled [U0]..[U{n - 1}].\n\n"
        f"{listing}\n\n"
        f"Split the lecture into between 2 and {max_sections} sections, one per main concept or topic, in order. "
        "For each section give a short descriptive title and the number of the unit where it starts "
        "(start_unit). The first section must start at 0."
    )
    data = llm.chat_json(prompt, OUTLINE_SCHEMA, system=SYSTEM, temperature=0.2)
    starts = {}
    for s in data.get("sections", []):
        try:
            k = int(s["start_unit"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= k < n and k not in starts:
            starts[k] = (s.get("title") or "").strip() or f"Part {len(starts) + 1}"
    if 0 not in starts:
        starts[0] = lecture_title or "Introduction"
    keys = sorted(starts)
    return [{"title": starts[k], "unit_ids": ids[k:keys[i + 1] if i + 1 < len(keys) else n]}
            for i, k in enumerate(keys)]


# ---------- 2. write the notes for one section ----------

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "short": {"type": "string"},
        "medium": {"type": "string"},
        "long": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "key_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"term": {"type": "string"}, "definition": {"type": "string"}},
                "required": ["term", "definition"],
            },
        },
        "best_images": {"type": "array", "items": {"type": "integer"}},
        "further_reading": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["short", "medium", "long", "key_points", "key_terms", "best_images", "further_reading"],
}


def section_material(units: list[dict], unit_ids: list[int]) -> str:
    chosen = [units[i] for i in unit_ids]
    per_unit = max(400, CFG.max_section_chars // max(len(chosen), 1))
    return "\n\n".join(unit_text(u, per_unit) for u in chosen)


def write_section(title: str, units: list[dict], unit_ids: list[int], lecture_title: str) -> dict:
    with_images = [i for i in unit_ids if units[i].get("image")]
    img_note = (f"Units with pictures: {', '.join(f'U{i}' for i in with_images)}. In best_images list the "
                "numbers (e.g. 3 for U3) of up to 3 whose pictures best help explain this section."
                if with_images else "There are no pictures; return best_images as [].")
    prompt = (
        f"Lecture: {lecture_title}\nSection: {title}\n\n"
        f"LECTURE MATERIAL FOR THIS SECTION\n{section_material(units, unit_ids)}\n\n"
        "Write study notes for this section, at three lengths:\n"
        "- short: 2–4 sentences, the core idea only.\n"
        "- medium: about 150–300 words in Markdown, the main ideas with a short example.\n"
        "- long: a full explanation of 500–1000 words in Markdown, with sub-headings (####), step-by-step "
        "reasoning, worked examples, formulas where relevant, and common mistakes. Refer to slides or "
        "timestamps (e.g. 'Slide 4', '12:30') where it helps.\n"
        "Also give key_points (4–8 bullet strings), key_terms (term + one-sentence definition), and "
        "further_reading: 2–4 well-known textbooks, papers or topics to look up (names only, no URLs).\n"
        f"{img_note}"
    )
    data = llm.chat_json(prompt, NOTES_SCHEMA, system=SYSTEM, temperature=0.3)
    data["best_images"] = [i for i in data.get("best_images", []) if i in with_images][:3] or with_images[:3]
    return data


def references(units: list[dict], unit_ids: list[int], sources: dict) -> list[dict]:
    """References built from the source material (not from the AI): slide numbers and timestamps."""
    refs = []
    slides = [units[i]["page"] for i in unit_ids if units[i].get("page")]
    if slides:
        rng = f"Slide {slides[0]}" if len(slides) == 1 else f"Slides {slides[0]}–{slides[-1]}"
        refs.append({"label": f"{rng} — {sources.get('pdf_name', 'lecture PDF')}", "url": None})
    yt = sources.get("youtube_url")
    for i in unit_ids:
        u = units[i]
        if u.get("start") is None or not u.get("speech"):
            continue
        when = f"{fmt_time(u['start'])}–{fmt_time(u['end'])}"
        if yt:
            sep = "&" if "?" in yt else "?"
            refs.append({"label": f"Video {when}", "url": f"{yt}{sep}t={int(u['start'])}s"})
        else:
            refs.append({"label": f"Recording {when} ({sources.get('media_name', 'audio')})", "url": None})
    return refs


def generate_sections(units: list[dict], lecture_title: str, sources: dict,
                      progress: Callable[[float, str], None] | None = None,
                      on_section: Callable[[list[dict]], None] | None = None,
                      existing: list[dict] | None = None, outline: list[dict] | None = None,
                      on_outline: Callable[[list[dict]], None] | None = None) -> list[dict]:
    """Writes notes for every section. To continue a stopped lecture, pass the sections already
    written (`existing`) and the saved `outline`; only the missing sections are written."""
    sections = list(existing or [])
    if outline is None:
        covered = {i for s in sections for i in s["unit_ids"]}
        rest = [u for u in units if u["id"] not in covered]
        if progress:
            progress(len(sections) / max(len(sections) + 1, 1), "Finding the main topics…")
        outline = [{"title": s["title"], "unit_ids": s["unit_ids"]} for s in sections]
        if rest:
            outline += make_outline(rest, lecture_title)
        if on_outline:
            on_outline(outline)
    for n, sec in enumerate(outline):
        if n < len(sections):
            continue  # already written
        if progress:
            progress(n / len(outline), f"Writing notes {n + 1}/{len(outline)}: {sec['title']}")
        notes = None
        for attempt in range(2):  # one retry if the model fails or gives a broken answer
            try:
                notes = write_section(sec["title"], units, sec["unit_ids"], lecture_title)
                break
            except llm.LLMError as e:
                err = str(e)
        if notes is None:  # keep going with the other sections
            msg = f"Notes for this section could not be written ({err[:200]}). The lecture text is in the Sources tab."
            notes = {"short": msg, "medium": msg, "long": msg, "key_points": [], "key_terms": [],
                     "best_images": [], "further_reading": [], "failed": True}
        sections.append({
            "id": n,
            "title": sec["title"],
            "unit_ids": sec["unit_ids"],
            "notes": notes,
            "references": references(units, sec["unit_ids"], sources),
            "quiz": None,
            "code": None,
        })
        if on_section:  # lets the caller save after every section
            on_section(sections)
    if progress:
        progress(1.0, "Notes done")
    return sections
