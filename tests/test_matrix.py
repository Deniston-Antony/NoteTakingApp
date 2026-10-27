"""Full test matrix on a real lecture: Cyrill Stachniss - Kalman Filter & EKF (YouTube, 74 min)
with its slides (moro01-08-ekf.pdf).

Phase 1 (formats): a 3-minute clip converted to many audio/video formats -> length, speech to text, frames.
Phase 2 (combinations): full pipeline for every input combination, with automatic checks.

Run:
  venv\\Scripts\\python.exe tests\\test_matrix.py               # everything
  venv\\Scripts\\python.exe tests\\test_matrix.py formats       # phase 1 only
  venv\\Scripts\\python.exe tests\\test_matrix.py pdf_only video_mp4   # chosen runs
Results: tests/results/report.md and results.json
"""
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import CFG  # noqa: E402
from core import code_generator, media, pipeline, storage, transcriber, youtube_processor  # noqa: E402
from core.timer import fmt_duration  # noqa: E402

URL = "https://www.youtube.com/watch?v=E-6paM_Iwfc"
PDF = ROOT / "moro01-08-ekf.pdf"
WORK = ROOT / "tests" / "samples" / "ekf"
RESULTS = ROOT / "tests" / "results"
WORK.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import os
    base = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages"
    hits = list(base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    if not hits:
        raise SystemExit("ffmpeg not found (needed only for making test files)")
    return str(hits[0])


FFMPEG = find_ffmpeg()


def ff(*args):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


# ---------------------------------------------------------------- source media
def source_media() -> tuple[Path, Path]:
    """Audio + video of the YouTube lecture (downloaded once, reused afterwards)."""
    a, v = WORK / "source_audio.m4a", WORK / "source_video.mp4"
    if not (a.exists() and v.exists()):
        for d in storage.LECTURES.glob("*kalman*"):  # reuse an earlier download if there is one
            ma, mv = d / "media" / "audio.m4a", d / "media" / "video.mp4"
            if ma.exists() and mv.exists() and mv.stat().st_size > 50_000_000:
                shutil.copy(ma, a)
                shutil.copy(mv, v)
                break
    if not (a.exists() and v.exists()):
        log("downloading source media from YouTube…")
        tmp = WORK / "dl"
        audio, video, _ = youtube_processor.download(URL, tmp)
        shutil.move(str(audio), a)
        shutil.move(str(video), v)
    return a, v


# ---------------------------------------------------------------- phase 1: formats
AUDIO_FORMATS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
    "wav_16k_mono (like the 🎙 recorder)": ["-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le"],
    "wav_48k_stereo": ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le"],
    "m4a": ["-c:a", "aac", "-b:a", "128k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "4"],
    "opus": ["-c:a", "libopus", "-b:a", "64k"],
    "flac": ["-c:a", "flac"],
    "webm": ["-c:a", "libopus", "-b:a", "64k"],
    "aac": ["-c:a", "aac", "-b:a", "128k"],
    "wma": ["-c:a", "wmav2", "-b:a", "128k"],
}
VIDEO_FORMATS = {
    "mp4": ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"],
    "mkv": ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "libopus"],
    "webm": ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "500k", "-c:a", "libopus"],
    "mov": ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"],
    "avi": ["-c:v", "mpeg4", "-q:v", "6", "-c:a", "libmp3lame"],
}


def words(text):
    return set(re.findall(r"[a-z]{4,}", text.lower()))


def phase_formats(audio_src: Path, video_src: Path) -> list[dict]:
    clip_a = WORK / "clip_source.m4a"
    clip_v = WORK / "clip_source.mp4"
    ff("-ss", "600", "-t", "180", "-i", str(audio_src), "-c", "copy", str(clip_a))
    ff("-ss", "600", "-t", "180", "-i", str(video_src), "-ss", "600", "-t", "180", "-i", str(audio_src),
       "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", str(clip_v))
    ref = transcriber.transcribe(clip_a)
    ref_words = words(" ".join(s["text"] for s in ref["segments"]))
    out = []

    def check(name, path, is_video):
        r = {"name": name, "file": path.name, "ok": False}
        try:
            t0 = time.time()
            r["size_kb"] = path.stat().st_size // 1024
            r["duration"] = round(media.duration(path) or 0, 1)
            tr = transcriber.transcribe(path)
            text = " ".join(s["text"] for s in tr["segments"])
            r["seconds"] = round(time.time() - t0, 1)
            r["words"] = len(text.split())
            r["language"] = tr["language"]
            w = words(text)
            r["match_vs_reference"] = round(len(w & ref_words) / max(len(ref_words), 1), 2)
            problems = []
            if not 170 <= r["duration"] <= 190:
                problems.append(f"length detected as {r['duration']}s (expected 180)")
            if r["words"] < 200:
                problems.append(f"only {r['words']} words transcribed")
            if tr["language"] != "en":
                problems.append(f"language detected as {tr['language']}")
            if r["match_vs_reference"] < 0.6:
                problems.append(f"transcript differs from reference ({r['match_vs_reference']})")
            if is_video:
                r["has_video"] = media.has_video(path)
                frame = WORK / f"frame_test_{path.suffix[1:]}.jpg"
                frame.unlink(missing_ok=True)
                r["frame_ok"] = media.extract_frame(path, 90, frame) and frame.stat().st_size > 5000
                if not r["has_video"]:
                    problems.append("video stream not found")
                if not r["frame_ok"]:
                    problems.append("could not grab a frame")
            r["problems"] = problems
            r["ok"] = not problems
        except Exception as e:
            r["problems"] = [f"{type(e).__name__}: {e}"]
        log(f"  {'PASS' if r['ok'] else 'FAIL'}  {name:38s} {r.get('words', 0):5} words  "
            f"match {r.get('match_vs_reference', '-')}  {r.get('seconds', '-')}s  {'; '.join(r['problems'])}")
        return r

    log("Phase 1a: audio formats")
    for name, args in AUDIO_FORMATS.items():
        ext = name.split("_")[0].split(" ")[0]
        path = WORK / f"clip_{name.split(' ')[0]}.{ext}"
        try:
            ff("-i", str(clip_a), "-vn", *args, str(path))
        except subprocess.CalledProcessError as e:
            out.append({"name": f"audio {name}", "ok": False, "problems": [f"ffmpeg failed: {e}"]})
            continue
        out.append(check(f"audio {name}", path, False))

    log("Phase 1b: video formats")
    for ext, args in VIDEO_FORMATS.items():
        path = WORK / f"clip_video.{ext}"
        try:
            ff("-i", str(clip_v), "-vf", "scale=-2:360", *args, str(path))
        except subprocess.CalledProcessError as e:
            out.append({"name": f"video {ext}", "ok": False, "problems": [f"ffmpeg failed: {e}"]})
            continue
        out.append(check(f"video {ext}", path, True))
    return out


# ---------------------------------------------------------------- phase 2: combinations
def make_full_files(audio_src: Path, video_src: Path) -> dict:
    files = {"mp3": WORK / "full_audio.mp3", "mp4": WORK / "full_video.mp4", "rec": WORK / "recording_5min.wav"}
    if not files["mp3"].exists():
        ff("-i", str(audio_src), "-vn", "-c:a", "libmp3lame", "-b:a", "96k", str(files["mp3"]))
    if not files["mp4"].exists():
        ff("-i", str(video_src), "-i", str(audio_src), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
           str(files["mp4"]))
    if not files["rec"].exists():  # what the in-app recorder produces, 5 minutes from the start
        ff("-t", "300", "-i", str(audio_src), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(files["rec"]))
    return files


def runs(files) -> dict:
    pdf = PDF.read_bytes()
    mp3, mp4, rec = files["mp3"].read_bytes(), files["mp4"].read_bytes(), files["rec"].read_bytes()
    I, O = pipeline.Inputs, pipeline.Options
    return {
        "pdf_only": (I("TEST pdf only", pdf_bytes=pdf, pdf_name=PDF.name), O()),
        "youtube": (I("TEST youtube", media_kind="youtube", youtube_url=URL), O()),
        "youtube_pdf_code": (I("TEST youtube + pdf (+code)", media_kind="youtube", youtube_url=URL,
                               pdf_bytes=pdf, pdf_name=PDF.name), O(make_code=True)),
        "youtube_whisper": (I("TEST youtube, whisper not captions", media_kind="youtube", youtube_url=URL),
                            O(use_captions=False)),
        "audio_mp3": (I("TEST audio mp3", media_kind="audio", media_bytes=mp3, media_name="lecture.mp3"), O()),
        "audio_mp3_pdf": (I("TEST audio mp3 + pdf", media_kind="audio", media_bytes=mp3, media_name="lecture.mp3",
                            pdf_bytes=pdf, pdf_name=PDF.name), O()),
        "video_mp4": (I("TEST video mp4", media_kind="video", media_bytes=mp4, media_name="lecture.mp4"), O()),
        "video_mp4_pdf": (I("TEST video mp4 + pdf", media_kind="video", media_bytes=mp4, media_name="lecture.mp4",
                            pdf_bytes=pdf, pdf_name=PDF.name), O()),
        "record_pdf": (I("TEST 5-min recording + pdf", media_kind="record", media_bytes=rec,
                         media_name="recording.wav", pdf_bytes=pdf, pdf_name=PDF.name), O()),
        "pdf_only_no_vision": (I("TEST pdf only, no picture reading", pdf_bytes=pdf, pdf_name=PDF.name),
                               O(describe_images=False, make_quiz=False)),
    }


def check_lecture(lec: dict, inp, opt) -> list[str]:
    p = []
    has_media = inp.media_kind != "none"
    secs = lec["sections"]
    if lec.get("status") != "done":
        p.append(f"status is {lec.get('status')}: {lec.get('error')}")
    if len(secs) < 2:
        p.append(f"only {len(secs)} section(s)")
    for s in secs:
        n = s["notes"]
        tag = f"section '{s['title'][:30]}'"
        if n.get("failed"):
            p.append(f"{tag}: notes failed")
            continue
        for lvl, lo in (("short", 10), ("medium", 80), ("long", 250)):
            if len(n.get(lvl, "").split()) < lo:
                p.append(f"{tag}: {lvl} has only {len(n.get(lvl, '').split())} words")
        if not (len(n["short"]) < len(n["medium"]) < len(n["long"])):
            p.append(f"{tag}: short/medium/long are not increasing in length")
        if not n.get("key_points"):
            p.append(f"{tag}: no key points")
        if not s.get("references"):
            p.append(f"{tag}: no references")
        for uid in n.get("best_images", []):
            u = lec["units"][uid]
            if not (u.get("image") and storage.asset_path(lec, u["image"]).exists()):
                p.append(f"{tag}: picture for unit {uid} missing")
        if opt.make_quiz:
            q = s.get("quiz")
            if not q or not q.get("mcq"):
                p.append(f"{tag}: no exam questions")
            else:
                for m in q["mcq"]:
                    if not 0 <= m["answer_index"] < len(m["options"]):
                        p.append(f"{tag}: bad MCQ answer index")
        if opt.make_code:
            c = s.get("code")
            if not c:
                p.append(f"{tag}: no python script")
            elif not c.get("verified"):
                p.append(f"{tag}: python script does not run")
    units = lec["units"]
    if inp.pdf_bytes:
        if len(units) != 64:
            p.append(f"expected 64 slide units, got {len(units)}")
        if opt.describe_images and not any(u.get("image_desc") for u in units):
            p.append("no slide pictures were described")
    if has_media and not lec["transcript"]:
        p.append("no transcript")
    if has_media and inp.pdf_bytes:
        with_speech = [u for u in units if u.get("speech")]
        starts = [u["start"] for u in units if u.get("start") is not None]
        if starts != sorted(starts):
            p.append("speech-to-slide matching goes backwards in time")
        share = len(with_speech) / len(units)
        if inp.media_kind != "record" and share < 0.4:
            p.append(f"only {len(with_speech)}/{len(units)} slides got speech")
    if (inp.media_kind == "video" or inp.media_kind == "youtube") and not inp.pdf_bytes:
        if not any(u.get("image") for u in units):
            p.append("no video frames")
    if inp.media_kind == "youtube":
        if not any(r.get("url") and "t=" in r["url"] for s in secs for r in s["references"]):
            p.append("no clickable YouTube timestamps")
    if not lec.get("timing"):
        p.append("no timing recorded")
    # exports
    try:
        md = storage.to_markdown(lec)
        html = storage.to_html(lec)
        if len(md) < 2000 or "<h2>" not in html:
            p.append("export looks empty")
        if "http" in html.split("<body>")[0]:
            p.append("HTML export loads something from the internet")
    except Exception as e:
        p.append(f"export failed: {e}")
    return p


def check_ui(lid: str, n_sections: int) -> list[str]:
    from streamlit.testing.v1 import AppTest
    p = []
    at = AppTest.from_file(str(ROOT / "NoteTakingApp.py"), default_timeout=120)
    at.session_state["view"] = lid
    at.run()
    p += [f"UI error: {e.value}" for e in at.exception]
    for i in range(1, n_sections):
        at.radio(key=f"sec_{lid}").set_value(i).run()
        p += [f"UI error in section {i + 1}: {e.value}" for e in at.exception]
    return p


def run_one(name, inp, opt) -> dict:
    log(f"\n=== {name}")
    r = {"name": name, "ok": False, "problems": []}
    etas = []
    last = {"stage": None}

    def progress(stage, frac, msg):
        if stage != last["stage"]:
            log(f"   [{time.strftime('%H:%M:%S')}] {msg}")
            last["stage"] = stage

    def on_time(elapsed, left):
        if left is not None:
            etas.append((round(elapsed), round(elapsed + left)))

    t0 = time.time()
    try:
        lec = pipeline.run(inp, opt, progress, on_time)
    except Exception as e:
        r["problems"].append(f"pipeline crashed: {type(e).__name__}: {e}")
        r["traceback"] = traceback.format_exc()
        log(r["traceback"])
        lec = None
    total = time.time() - t0
    r["seconds"] = round(total)
    if lec:
        r["lecture_id"] = lec["id"]
        r["sections"] = len(lec["sections"])
        r["units"] = len(lec["units"])
        r["slides_with_speech"] = sum(1 for u in lec["units"] if u.get("speech")) if inp.pdf_bytes else None
        r["timing"] = lec.get("timing")
        r["problems"] += check_lecture(lec, inp, opt)
        try:
            r["problems"] += check_ui(lec["id"], len(lec["sections"]))
        except Exception as e:
            r["problems"].append(f"UI test crashed: {e}")
        # how good was the time estimate at 25% / 50% of the run
        for frac in (0.25, 0.5):
            pick = [p for e, p in etas if e >= frac * total]
            if pick:
                r[f"predicted_total_at_{int(frac * 100)}pct"] = pick[0]
    r["ok"] = not r["problems"]
    log(f"   {'PASS' if r['ok'] else 'FAIL'} in {fmt_duration(total)}  sections={r.get('sections')}  "
        f"problems: {r['problems'][:6]}")
    return r


# ---------------------------------------------------------------- report
def write_report(results: dict):
    (RESULTS / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    L = ["# Test report — Kalman Filter & EKF lecture", f"*{time.strftime('%Y-%m-%d %H:%M')}*", ""]
    if results.get("formats"):
        L += ["## Phase 1: file formats (3-minute clip)", "",
              "| Format | Result | Words | Match vs reference | Time | Problems |", "|---|---|---|---|---|---|"]
        for r in results["formats"]:
            L.append(f"| {r['name']} | {'✅' if r['ok'] else '❌'} | {r.get('words', '')} | "
                     f"{r.get('match_vs_reference', '')} | {r.get('seconds', '')} s | {'; '.join(r['problems'])} |")
        L.append("")
    if results.get("runs"):
        L += ["## Phase 2: input combinations (full 74-minute lecture)", "",
              "| Run | Result | Time | Sections | Slides with speech | Estimate at 25% / 50% | Problems |",
              "|---|---|---|---|---|---|---|"]
        for r in results["runs"]:
            est = " / ".join(fmt_duration(r[k]) for k in ("predicted_total_at_25pct", "predicted_total_at_50pct")
                             if r.get(k))
            sws = f"{r['slides_with_speech']}/{r['units']}" if r.get("slides_with_speech") is not None else ""
            L.append(f"| {r['name']} | {'✅' if r['ok'] else '❌'} | {fmt_duration(r.get('seconds'))} | "
                     f"{r.get('sections', '')} | {sws} | {est} | {'; '.join(r['problems'][:8])} |")
    (RESULTS / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv):
    audio_src, video_src = source_media()
    log(f"source: {audio_src.name} {media.duration(audio_src):.0f}s, {video_src.name}")
    results_path = RESULTS / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else {}
    want = set(argv)
    if not want or "formats" in want:
        results["formats"] = phase_formats(audio_src, video_src)
        write_report(results)
    files = make_full_files(audio_src, video_src)
    all_runs = runs(files)
    chosen = [k for k in all_runs if not want or k in want]
    prev = {r["name"]: r for r in results.get("runs", [])}
    for name in chosen:
        prev[name] = run_one(name, *all_runs[name])
        results["runs"] = [prev[k] for k in all_runs if k in prev]
        write_report(results)
    log("\nREPORT: " + str(RESULTS / "report.md"))


if __name__ == "__main__":
    main(sys.argv[1:])
