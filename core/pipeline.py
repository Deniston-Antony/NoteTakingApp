"""Runs all the steps: inputs -> transcript / slides -> units -> notes -> questions -> code.

A run can continue a lecture that stopped part-way: steps whose results are already saved
(transcript + slides = "units", finished sections, exam questions) are skipped."""
import math
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from config import CFG
from core import (aligner, code_generator, llm, media, pdf_processor, quiz_generator,
                  storage, timer, transcriber, vision, youtube_processor)
from core.notes_generator import fmt_time, generate_sections


@dataclass
class Inputs:
    title: str
    media_kind: str = "none"            # none | record | audio | video | youtube
    media_bytes: bytes | None = None
    media_name: str | None = None
    youtube_url: str | None = None
    pdf_bytes: bytes | None = None
    pdf_name: str | None = None


@dataclass
class Options:
    language: str | None = None         # None = auto-detect
    describe_images: bool = True        # use the vision model on slides / video frames
    use_captions: bool = True           # YouTube: use the video's captions when available
    make_quiz: bool = True
    make_code: bool = False             # Python scripts for every section now (slower)


class Cancelled(Exception):
    """Raised when the user presses Cancel."""


Progress = Callable[[str, float, str], None]  # (stage, fraction 0-1, message)
OnTime = Callable[[float, float | None], None]  # (seconds elapsed, estimated seconds left or None)


def _noop(stage, frac, msg):
    pass


def inputs_from_saved(lec: dict) -> Inputs:
    """Rebuilds the inputs of a lecture from the files saved in its media folder (for Resume)."""
    info = lec.get("inputs") or {}
    src = lec.get("sources", {})
    media_dir = storage.lecture_dir(lec["id"]) / "media"
    kind = info.get("media_kind") or ("youtube" if src.get("youtube_url") else "none")
    inp = Inputs(title=lec["title"], media_kind=kind, media_name=info.get("media_name") or src.get("media_name"),
                 youtube_url=info.get("youtube_url") or src.get("youtube_url"))
    if kind in ("record", "audio", "video"):
        files = sorted(media_dir.glob(f"{kind}.*"))
        if files:
            inp.media_bytes = files[0].read_bytes()
        else:
            inp.media_kind = "none"
    pdf = media_dir / "slides.pdf"
    if pdf.exists():
        inp.pdf_bytes, inp.pdf_name = pdf.read_bytes(), src.get("pdf_name") or "slides.pdf"
    return inp


def run(inp: Inputs, opt: Options, progress: Progress = _noop, on_time: OnTime | None = None,
        lec: dict | None = None, cancel: threading.Event | None = None) -> dict:
    est = timer.Estimator()
    resuming = bool(lec and lec.get("units"))
    known = {"media": inp.media_kind != "none" and not resuming, "dur": None, "captions": False,
             "pages": None, "slide_imgs": None, "video": False, "units": None, "sections": None,
             "sections_done": 0, "outline_done": False, "quiz_done": 0, "code_done": 0}

    def replan():
        """Re-estimates the remaining steps from what is known so far."""
        k = known
        if k["media"] and k["dur"] is None and not k["captions"]:
            est.ready = False  # YouTube before the download: length not known yet
            return
        if k["media"] and not k["captions"]:
            if "transcribe" not in est.finished:
                est.set("transcribe", timer.WHISPER_LOAD + (k["dur"] or 0) / timer.WHISPER_SPEED)
        else:
            est.drop("transcribe")
        if k["pages"] is not None and not resuming and "pdf" not in est.finished:
            est.set("pdf", 1 + k["pages"] * 0.15)
        units = k["units"] or k["pages"] or math.ceil((k["dur"] or 0) / (CFG.segment_minutes * 60)) or 1
        n_img = 0
        if opt.describe_images and not resuming:
            if k["pages"]:
                n_img = k["slide_imgs"] if k["slide_imgs"] is not None else round(k["pages"] * 0.3)
            elif k["video"]:
                n_img = units
        if n_img and "vision" not in est.finished:
            est.set("vision", timer.VISION_LOAD + n_img * timer.VISION_PER_IMAGE)
        elif not n_img:
            est.drop("vision")
        if k["pages"] and k["media"] and "align" not in est.finished:
            est.set("align", timer.ALIGN)
        n_sec = k["sections"] or max(timer.guess_sections(units), k["sections_done"])
        if "notes" not in est.finished:
            todo = max(n_sec - k["sections_done"], 0)
            est.set("notes", (0 if k["outline_done"] else timer.OUTLINE) + todo * timer.NOTES_PER_SECTION)
        extras = ((n_sec - k["quiz_done"]) * timer.QUIZ_PER_SECTION if opt.make_quiz else 0) + \
                 ((n_sec - k["code_done"]) * timer.CODE_PER_SECTION if opt.make_code else 0)
        if extras > 0:
            est.set("extras", extras)
        else:
            est.drop("extras")
        est.ready = True

    def report(stage, frac, msg):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        est.enter(stage)
        progress(stage, frac, msg)
        if on_time:
            on_time(est.elapsed(), est.remaining(frac))

    if inp.pdf_bytes and not resuming:
        try:
            import pymupdf
            with pymupdf.open(stream=inp.pdf_bytes, filetype="pdf") as doc:
                known["pages"] = len(doc)
        except Exception:
            known["pages"] = 1

    if lec is None:
        lec = storage.new_lecture(inp.title or "Untitled lecture")
    prev_total = (lec.get("timing") or {}).get("total", 0) if resuming else 0  # time before a stop
    lec["status"] = "processing"
    lec.pop("error", None)
    lec["options"] = asdict(opt)
    lec["inputs"] = {"media_kind": inp.media_kind, "media_name": inp.media_name,
                     "youtube_url": inp.youtube_url, "pdf_name": inp.pdf_name}
    d = storage.lecture_dir(lec["id"])
    assets, media_dir = d / "assets", d / "media"
    assets.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    src = lec["sources"]
    storage.save(lec)

    try:
        if not resuming:
            units = _build_units(inp, opt, lec, src, assets, media_dir, known, replan, report, est, on_time)
        else:
            units = lec["units"]
            secs = lec.get("sections") or []
            known.update(units=len(units), sections_done=len(secs), outline_done=bool(lec.get("outline")),
                         quiz_done=sum(1 for s in secs if s.get("quiz")),
                         code_done=sum(1 for s in secs if s.get("code")))
            if lec.get("outline"):
                known["sections"] = len(lec["outline"])
            replan()
            report("notes", 0.0, f"Continuing: {len(secs)} section(s) already written…")

        # ---- 4. notes ----
        def save_sections(secs):
            lec["sections"] = secs
            storage.save(lec)

        def save_outline(outline):
            lec["outline"] = outline
            known["sections"], known["outline_done"] = len(outline), True
            replan()
            storage.save(lec)

        lec["sections"] = generate_sections(
            units, lec["title"], src, lambda f, m: report("notes", f, m), save_sections,
            existing=lec.get("sections") or [], outline=lec.get("outline"), on_outline=save_outline)
        known["sections"] = len(lec["sections"])
        known["sections_done"] = len(lec["sections"])
        replan()
        storage.save(lec)

        # ---- 5. exam questions / code (only for sections that don't have them yet) ----
        n = len(lec["sections"])
        for i, s in enumerate(lec["sections"]):
            if s["notes"].get("failed"):
                continue
            if opt.make_quiz and not s.get("quiz"):
                report("extras", i / n, f"Writing exam questions {i + 1}/{n}…")
                try:
                    s["quiz"] = quiz_generator.generate_quiz(s, lec["title"])
                except llm.LLMError:
                    s["quiz"] = None  # can be made later from the Exam questions tab
                storage.save(lec)
            if opt.make_code and not s.get("code"):
                report("extras", (i + 0.5) / n, f"Writing Python script {i + 1}/{n}…")
                try:
                    s["code"] = code_generator.generate_code(s, lec["title"], run_name=f"{lec['id']}_{i}")
                except llm.LLMError:
                    s["code"] = None  # can be made later from the Python Lab tab
                storage.save(lec)

        lec["status"] = "done"
        lec["timing"] = _timing(est, prev_total)
        storage.save(lec)
        progress("done", 1.0, "Finished in " + timer.fmt_duration(lec["timing"]["total"]))
        return lec
    except Cancelled:
        lec["status"] = "stopped"
        lec["timing"] = _timing(est, prev_total)
        storage.save(lec)
        raise
    except Exception as e:
        lec["status"] = "error"
        lec["error"] = str(e)
        lec["timing"] = _timing(est, prev_total)
        storage.save(lec)
        raise


def _timing(est, prev_total: float) -> dict:
    t = est.summary()
    t["total"] = round(t["total"] + prev_total, 1)
    return t


def _build_units(inp, opt, lec, src, assets, media_dir, known, replan, report, est, on_time) -> list[dict]:
    """Steps 1-3: media -> transcript, PDF -> slides, then the "units" the notes are written from."""
    # ---- 1. media: save / download, then transcript ----
    media_path, video_path, segments = None, None, None
    if inp.media_kind in ("record", "audio", "video") and inp.media_bytes:
        ext = Path(inp.media_name or "recording.wav").suffix or ".wav"
        media_path = media_dir / f"{inp.media_kind}{ext}"
        media_path.write_bytes(inp.media_bytes)
        src["media_name"] = inp.media_name or "recording"
        if inp.media_kind == "video" and media.has_video(media_path):
            video_path = media_path
        known["dur"] = media.duration(media_path) or 0
        known["video"] = video_path is not None
    replan()
    if on_time:
        on_time(est.elapsed(), est.remaining())
    if inp.media_kind == "youtube" and inp.youtube_url:
        report("download", 0.0, "Downloading the YouTube video (needs internet)…")
        # video frames are only used when there are no slides
        media_path, video_path, meta = youtube_processor.download(
            inp.youtube_url, media_dir, want_video=not inp.pdf_bytes)
        src.update(youtube_url=meta["url"], youtube_title=meta["title"], youtube_channel=meta["channel"],
                   media_name=meta["title"])
        if opt.use_captions and meta.get("id"):
            report("download", 0.9, "Looking for captions…")
            segments = youtube_processor.fetch_captions(meta["id"])
            if segments:
                src["transcript_from"] = "YouTube captions"
                known["captions"] = True
        known["dur"] = meta.get("duration") or media.duration(media_path) or 0
        known["video"] = video_path is not None
        replan()
        report("download", 1.0, "Video downloaded")

    if media_path and not segments:
        report("transcribe", 0.0, "Converting speech to text (Whisper)…")
        for m in (CFG.text_model, CFG.vision_model):  # give Whisper the whole GPU
            llm.unload(m)
        result = transcriber.transcribe(
            media_path, opt.language,
            lambda f: report("transcribe", f, f"Converting speech to text… {int(f * 100)}%"))
        segments = result["segments"]
        lec["language"] = result["language"]
        src["transcript_from"] = f"Whisper {CFG.whisper_model}"
    lec["transcript"] = segments or []
    storage.save(lec)

    # ---- 2. slides ----
    slides = []
    if inp.pdf_bytes:
        pdf_path = media_dir / "slides.pdf"
        pdf_path.write_bytes(inp.pdf_bytes)
        src["pdf_name"] = inp.pdf_name or "slides.pdf"
        report("pdf", 0.0, "Reading the PDF…")
        slides = pdf_processor.process_pdf(pdf_path, assets, lambda f: report("pdf", f, "Reading the PDF…"))
        if opt.describe_images:
            todo = [s for s in slides if s["has_images"] or len(s["text"]) < 40]
            known["pages"], known["slide_imgs"] = len(slides), len(todo)
            replan()
            for i, s in enumerate(todo):
                report("vision", i / len(todo), f"Looking at slide pictures {i + 1}/{len(todo)}…")
                s["image_desc"] = vision.describe(assets / s["image"], "lecture slide")

    # ---- 3. build units ----
    units = []
    if slides:
        for i, s in enumerate(slides):
            units.append({"id": i, "kind": "slide", "label": f"Slide {s['page']}", "page": s["page"],
                          "slide_text": s["text"], "image": s["image"], "image_desc": s.get("image_desc", ""),
                          "speech": "", "start": None, "end": None})
        if segments:
            report("align", 0.0, "Matching the speech to the slides…")
            chunks = aligner.chunk_segments(segments, CFG.align_chunk_seconds)
            for chunk, k in zip(chunks, aligner.align(chunks, slides)):
                u = units[k]
                u["speech"] = (u["speech"] + " " + chunk["text"]).strip()
                u["start"] = chunk["start"] if u["start"] is None else u["start"]
                u["end"] = chunk["end"]
    elif segments:
        chunks = aligner.chunk_segments(segments, CFG.segment_minutes * 60)
        for i, c in enumerate(chunks):
            u = {"id": i, "kind": "segment", "label": f"{fmt_time(c['start'])}–{fmt_time(c['end'])}",
                 "slide_text": "", "image": None, "image_desc": "", "speech": c["text"],
                 "start": c["start"], "end": c["end"]}
            if video_path:
                name = f"frame_{i:03d}.jpg"
                if media.extract_frame(video_path, (c["start"] + c["end"]) / 2, assets / name):
                    u["image"] = name
                    if opt.describe_images:
                        report("vision", i / len(chunks), f"Looking at the video {i + 1}/{len(chunks)}…")
                        u["image_desc"] = vision.describe(assets / name, "video frame")
            units.append(u)
    if not units:
        raise ValueError("Nothing to make notes from: no speech was found and no PDF was given.")
    lec["units"] = units
    known["units"] = len(units)
    replan()
    llm.unload(CFG.vision_model)  # free GPU memory so the text model fits fully on the GPU
    llm.unload(CFG.embed_model)
    storage.save(lec)
    return units
