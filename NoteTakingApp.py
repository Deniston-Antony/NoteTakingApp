"""Offline Lecture Notes app.  Start with:  streamlit run NoteTakingApp.py"""
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Lecture Notes (offline)", page_icon="📝", layout="wide")

from config import CFG  # noqa: E402
from core import code_generator, code_runner, gpu, jobs, llm, pipeline, quiz_generator, storage  # noqa: E402
from core.timer import STAGE_NAMES, fmt_duration  # noqa: E402
from core.notes_generator import fmt_time  # noqa: E402

try:
    from streamlit_ace import st_ace
except Exception:  # editor package missing: fall back to a plain text box
    st_ace = None

ss = st.session_state
ss.setdefault("view", "new")


# ---------------------------------------------------------------- progress / timer helpers
def clock(sec: float | None) -> str:
    if sec is None:
        return "–"
    sec = int(max(sec, 0))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def time_line(job: jobs.Job) -> str:
    if job.state == "queued":
        return "⏳ Waiting in the queue (another lecture is using the GPU)"
    left = job.live_left()
    text = f"⏱ Elapsed **{clock(job.live_elapsed())}**"
    if left is None:
        return text + " · Estimating time left…"
    if left < 2:
        return text + " · Almost done…"
    finish = (datetime.now() + timedelta(seconds=left)).strftime("%H:%M")
    return text + f" · About **{clock(left)}** left · Expected finish ≈ **{finish}**"


def lecture_state(lid: str, status: str | None) -> str:
    """running | queued | stopped | done | error"""
    job = jobs.get(lid)
    if job and job.active:
        return job.state
    if status == "processing":
        return "stopped"  # the app was closed or restarted while it was working
    return status or "stopped"


ICONS = {"done": "📘", "error": "⚠️", "running": "⏳", "queued": "🕒", "stopped": "⏸"}


# ---------------------------------------------------------------- sidebar
@st.fragment(run_every=3)
def running_box():
    """Live list of lectures being generated; refreshes every 3 seconds on any page."""
    active = jobs.active()
    if not active:
        if ss.get("had_jobs"):  # something just finished: refresh the whole page once
            ss.had_jobs = False
            st.rerun()
        return
    ss.had_jobs = True
    st.subheader("Running now")
    for job in active:
        with st.container(border=True):
            st.markdown(f"**{job.title}**")
            st.progress(job.overall(), text=job.message[:70])
            st.caption(time_line(job).replace("**", ""))
            if ss.view != job.lecture_id and st.button("Open", key=f"run_open_{job.lecture_id}",
                                                       width="stretch"):
                ss.view = job.lecture_id
                st.rerun()


NO_FOLDER = "— Not in a folder —"


def lecture_button(lec):
    icon = ICONS.get(lecture_state(lec["id"], lec["status"]), "⏸")
    current = ss.view == lec["id"]
    if st.button(f"{icon} {lec['title']}", key=f"open_{lec['id']}", width="stretch",
                 help=lec["created"], type="primary" if current else "secondary"):
        ss.view = lec["id"]
        st.rerun()


def folder_tools(name: str, n: int):
    """Rename / delete menu for one folder."""
    with st.popover("⚙ Folder options", width="stretch"):
        new = st.text_input("Rename to", value=name, key=f"ren_{name}")
        if st.button("Rename", key=f"ren_btn_{name}"):
            try:
                storage.rename_folder(name, new)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        st.markdown("---")
        st.caption(f"Deleting the folder keeps its {n} lecture(s); they move to 'Not in a folder'.")
        if st.button("🗑 Delete folder", key=f"del_folder_{name}"):
            storage.delete_folder(name)
            st.rerun()


def library():
    """Saved lectures, grouped into folders, with search, new-folder and move tools."""
    st.subheader("Saved lectures")
    lectures = storage.list_lectures()
    folder_names = storage.folders()

    query = st.text_input("Search", placeholder="🔍 Search lectures", label_visibility="collapsed",
                          key="lib_search").strip().lower()
    if query:
        lectures = [l for l in lectures if query in l["title"].lower() or query in (l["folder"] or "").lower()]

    c1, c2 = st.columns(2)
    with c1:
        with st.popover("📁 New folder", width="stretch"):
            name = st.text_input("Folder name", key="new_folder_name", placeholder="e.g. Robotics")
            if st.button("Create folder", type="primary"):
                try:
                    storage.create_folder(name)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    with c2:
        with st.popover("🗂 Move", width="stretch", disabled=not storage.list_lectures()):
            all_lecs = storage.list_lectures()
            titles = {l["id"]: f"{l['title']}  ({l['folder'] or 'no folder'})" for l in all_lecs}
            pick = st.multiselect("Lectures to move", list(titles), format_func=titles.get, key="move_pick")
            st.selectbox("Move to", [NO_FOLDER] + folder_names, key="move_dest")
            def do_move():
                storage.move(ss.move_pick, None if ss.move_dest == NO_FOLDER else ss.move_dest)
                ss.move_pick = []  # clear the selection after moving

            st.button("Move", type="primary", disabled=not pick, on_click=do_move)
            if not folder_names:
                st.caption("Create a folder first with 📁 New folder.")

    if not lectures:
        st.caption("No lectures match." if query else "None yet")
    current_folder = next((l["folder"] for l in lectures if l["id"] == ss.view), None)
    for name in folder_names:
        inside = [l for l in lectures if l["folder"] == name]
        if query and not inside:
            continue
        with st.expander(f"📁 {name}  ({len(inside)})", expanded=bool(query) or name == current_folder):
            if not inside:
                st.caption("Empty. Use 🗂 Move, or 📁 Folder on a lecture's page.")
            for lec in inside:
                lecture_button(lec)
            folder_tools(name, len(inside))
    loose = [l for l in lectures if not l["folder"]]
    if loose and folder_names:
        st.caption("Not in a folder")
    for lec in loose:
        lecture_button(lec)


NEW_FOLDER = "➕ New folder…"


def folder_picker(lid: str):
    """'📁 Folder' box on a lecture's page: moves the lecture as soon as you pick a folder."""
    names = storage.folders()
    options = [NO_FOLDER] + names + [NEW_FOLDER]
    current = storage.folder_of(lid) or NO_FOLDER
    key = f"folder_{lid}"

    def changed():
        choice = ss[key]
        if choice in (NEW_FOLDER,):
            return  # wait for the name below
        storage.move([lid], None if choice == NO_FOLDER else choice)

    if ss.get(key) != NEW_FOLDER:  # always show where the lecture is now (it may have been moved elsewhere)
        ss[key] = current
    st.selectbox("📁 Folder", options, key=key, on_change=changed)
    if ss[key] == NEW_FOLDER:
        name = st.text_input("New folder name", key=f"newf_{lid}", placeholder="e.g. Robotics")
        if st.button("Create and move here", key=f"newf_btn_{lid}", type="primary"):
            try:
                made = storage.create_folder(name)
                storage.move([lid], made)
                del ss[key]
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def sidebar():
    with st.sidebar:
        st.title("📝 Lecture Notes")
        st.caption("Runs fully offline on this PC")
        if st.button("➕ New lecture", width="stretch", type="primary"):
            ss.view = "new"
            st.rerun()

        running_box()

        library()

        with st.expander("System status"):
            if llm.is_running():
                st.success("Ollama is running")
                missing = llm.missing_models()
                if missing:
                    st.error("Missing models: " + ", ".join(missing) + "\n\nRun `ollama pull <name>`.")
                else:
                    st.write(f"Text: `{CFG.text_model}`  \nVision: `{CFG.vision_model}`  \n"
                             f"Embeddings: `{CFG.embed_model}`")
            else:
                st.error("Ollama is not running. Start the Ollama app, then refresh.")
            st.write(f"Speech: `whisper {CFG.whisper_model}`")
            gpu.setup_cuda()
            st.write("GPU for Whisper: " + ("✅ yes" if gpu.cuda_available() else "❌ no (using CPU, slower)"))


# ---------------------------------------------------------------- new lecture page
MEDIA_CHOICES = {"none": "None", "record": "🎙 Record", "audio": "📁 Upload audio",
                 "youtube": "▶ YouTube link", "video": "🎞 Upload video"}


def new_lecture_page():
    st.header("New lecture")
    if not llm.is_running():
        st.error("Ollama is not running. Open the **Ollama** app (Start menu), then refresh this page.")
        return

    title = st.text_input("Lecture title", placeholder="e.g. Week 3 — Linear Regression")

    st.subheader("1. Lecture audio or video (optional)")
    kind = st.radio("Source", list(MEDIA_CHOICES), format_func=MEDIA_CHOICES.get, horizontal=True,
                    label_visibility="collapsed")
    media_bytes = media_name = youtube_url = None
    if kind == "record":
        rec = st.audio_input("Press the mic to start and stop recording")
        if rec:
            media_bytes, media_name = rec.getvalue(), "recording.wav"
    elif kind == "audio":
        f = st.file_uploader("Audio file", type=["mp3", "wav", "m4a", "ogg", "flac", "webm", "aac", "wma", "opus"])
        if f:
            media_bytes, media_name = f.getvalue(), f.name
    elif kind == "video":
        f = st.file_uploader("Video file (fully offline)", type=["mp4", "mkv", "mov", "webm", "avi"])
        if f:
            media_bytes, media_name = f.getvalue(), f.name
    elif kind == "youtube":
        youtube_url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=…")
        st.caption("Downloading the video needs internet. Everything after that runs on this PC.")

    st.subheader("2. Lecture slides PDF (optional)")
    pdf = st.file_uploader("PDF", type=["pdf"], label_visibility="collapsed")
    if pdf and kind != "none":
        st.caption("✅ The speech will be matched to the slides it talks about.")

    with st.expander("Options"):
        langs = {"Auto-detect": None, "English": "en", "Hindi": "hi", "Tamil": "ta", "Spanish": "es",
                 "French": "fr", "German": "de", "Chinese": "zh", "Arabic": "ar"}
        language = langs[st.selectbox("Spoken language", list(langs))]
        describe = st.checkbox("Look at slide pictures and video frames (better notes, slower)", True)
        captions = st.checkbox("YouTube: use the video's captions if it has them (faster)", True)
        quiz = st.checkbox("Create exam questions now", True)
        code = st.checkbox("Create Python scripts for every section now (slower; can also do it later)", False)

    busy = jobs.active()
    if busy:
        st.info(f"⏳ **{busy[0].title}** is being generated. A new lecture will wait in the queue and "
                "start automatically when it finishes.")

    if st.button("✨ Generate notes", type="primary"):
        has_media = bool(media_bytes) or (kind == "youtube" and youtube_url)
        if not has_media and not pdf:
            st.warning("Add audio, a video, a YouTube link or a PDF first.")
            return
        if kind == "youtube" and youtube_url and not pipeline.youtube_processor.video_id(youtube_url):
            st.warning("That doesn't look like a YouTube link.")
            return
        inp = pipeline.Inputs(
            title=title.strip() or (Path(pdf.name).stem if pdf else media_name or "Untitled lecture"),
            media_kind=kind if has_media else "none", media_bytes=media_bytes, media_name=media_name,
            youtube_url=youtube_url, pdf_bytes=pdf.getvalue() if pdf else None, pdf_name=pdf.name if pdf else None)
        opt = pipeline.Options(language=language, describe_images=describe, use_captions=captions,
                               make_quiz=quiz, make_code=code)
        ss.view = jobs.start(inp, opt)  # runs in the background; open its page to watch it
        st.rerun()


# ---------------------------------------------------------------- lecture page
def show_images(lec, unit_ids, cols=2):
    items = [lec["units"][i] for i in unit_ids if lec["units"][i].get("image")]
    items = [u for u in items if storage.asset_path(lec, u["image"]).exists()]
    for row in range(0, len(items), cols):
        for col, u in zip(st.columns(cols), items[row:row + cols]):
            col.image(str(storage.asset_path(lec, u["image"])), caption=u["label"], width="stretch")


def notes_tab(lec, sec):
    n = sec["notes"]
    level = st.segmented_control("Explanation length", ["Short", "Medium", "Long"], default="Medium",
                                 key=f"lvl_{lec['id']}_{sec['id']}") or "Medium"
    st.markdown(n[level.lower()])

    if n.get("best_images"):
        st.markdown("#### Pictures")
        show_images(lec, n["best_images"])

    c1, c2 = st.columns(2)
    with c1:
        if n.get("key_points"):
            st.markdown("#### Key points")
            st.markdown("\n".join(f"- {p}" for p in n["key_points"]))
    with c2:
        if n.get("key_terms"):
            st.markdown("#### Key terms")
            st.markdown("\n".join(f"- **{t['term']}**: {t['definition']}" for t in n["key_terms"]))

    if sec.get("references"):
        st.markdown("#### References")
        st.markdown("\n".join(f"- [{r['label']}]({r['url']})" if r.get("url") else f"- {r['label']}"
                              for r in sec["references"]))
    if n.get("further_reading"):
        st.markdown("#### Further reading")
        st.caption("Suggested by the AI: please check these before relying on them.")
        st.markdown("\n".join(f"- {r}" for r in n["further_reading"]))

    others = [i for i in sec["unit_ids"] if i not in n.get("best_images", [])]
    if any(lec["units"][i].get("image") for i in others):
        with st.expander("All slides / frames in this section"):
            show_images(lec, others, cols=3)


def quiz_tab(lec, sec):
    key = f"{lec['id']}_{sec['id']}"
    q = sec.get("quiz")
    if not q:
        st.info("No exam questions yet for this section.")
        if st.button("Create exam questions", key=f"mkquiz_{key}", type="primary"):
            with st.spinner("Writing questions…"):
                sec["quiz"] = quiz_generator.generate_quiz(sec, lec["title"])
                storage.save(lec)
            st.rerun()
        return

    if q.get("mcq"):
        st.markdown("#### Multiple choice")
        score = 0
        for i, m in enumerate(q["mcq"]):
            pick = st.radio(f"**{i + 1}. {m['question']}**", range(len(m["options"])),
                            format_func=lambda j, m=m: f"{'ABCDEF'[j]}) {m['options'][j]}",
                            index=None, key=f"mcq_{key}_{i}")
            if pick is not None:
                if pick == m["answer_index"]:
                    score += 1
                    st.success("Correct! " + m["explanation"])
                else:
                    st.error(f"Not quite. Answer: {'ABCDEF'[m['answer_index']]}. {m['explanation']}")
        st.caption(f"Score: {score}/{len(q['mcq'])}")

    if q.get("short_answer"):
        st.markdown("#### Short answer")
        for i, item in enumerate(q["short_answer"]):
            st.markdown(f"**{i + 1}. {item['question']}**")
            st.text_area("Your answer", key=f"sa_{key}_{i}", height=80, label_visibility="collapsed")
            with st.expander("Show model answer"):
                st.markdown(item["answer"])

    if q.get("long_answer"):
        st.markdown("#### Long answer")
        for i, item in enumerate(q["long_answer"]):
            st.markdown(f"**{i + 1}. {item['question']}**")
            with st.expander("Show model answer"):
                st.markdown(item["answer"])

    if st.button("🔄 New set of questions", key=f"reqz_{key}"):
        with st.spinner("Writing questions…"):
            sec["quiz"] = quiz_generator.generate_quiz(sec, lec["title"])
            storage.save(lec)
        for k in [k for k in ss if str(k).startswith((f"mcq_{key}_", f"sa_{key}_"))]:
            del ss[k]
        st.rerun()


def code_tab(lec, sec):
    key = f"{lec['id']}_{sec['id']}"
    run_name = key
    c = sec.get("code")
    request = st.text_input("What should the script do? (optional)", key=f"req_{key}",
                            placeholder="e.g. plot the function, simulate 1000 trials, compare two methods…")
    if not c:
        st.info("Create a runnable Python script that helps explain this section.")
        if st.button("🐍 Create Python script", key=f"mkcode_{key}", type="primary"):
            with st.spinner("Writing and testing the script…"):
                sec["code"] = code_generator.generate_code(sec, lec["title"], request, run_name)
                storage.save(lec)
            st.rerun()
        return

    st.markdown(f"### {c['title']}")
    st.markdown(f"**Goal:** {c['goal']}")
    if c.get("verified"):
        st.caption("✅ This script was tested and runs without errors.")
    else:
        st.caption("⚠️ The AI could not make this script run cleanly. Check the error output below.")

    ver = ss.setdefault(f"codever_{key}", 0)
    if st_ace:
        script = st_ace(value=c["script"], language="python", theme="monokai", font_size=14, height=420,
                        auto_update=True, key=f"ace_{key}_{ver}")
    else:
        script = st.text_area("Script", c["script"], height=420, key=f"ace_{key}_{ver}")
    script = script if script is not None else c["script"]

    b1, b2, b3, b4 = st.columns(4)
    run = b1.button("▶ Run", key=f"run_{key}", type="primary", width="stretch")
    if b2.button("💾 Save my edits", key=f"save_{key}", width="stretch"):
        c["script"] = script
        storage.save(lec)
        st.toast("Saved")
    if b3.button("↩ Reset to saved", key=f"reset_{key}", width="stretch"):
        ss[f"codever_{key}"] = ver + 1
        ss.pop(f"result_{key}", None)
        st.rerun()
    if b4.button("🔄 New script", key=f"regen_{key}", width="stretch"):
        with st.spinner("Writing and testing a new script…"):
            sec["code"] = code_generator.generate_code(sec, lec["title"], request, run_name)
            storage.save(lec)
        ss[f"codever_{key}"] = ver + 1
        ss.pop(f"result_{key}", None)
        st.rerun()

    with st.expander("Input for the script (only if it reads from input())"):
        stdin_text = st.text_area("One value per line", key=f"stdin_{key}", height=80)

    if run:
        with st.spinner("Running…"):
            ss[f"result_{key}"] = code_runner.run_script(script, run_name, stdin_text)

    res = ss.get(f"result_{key}")
    if res:
        st.markdown("#### Output")
        if res["returncode"] == 0:
            st.caption(f"✅ Finished in {res['seconds']} s")
        else:
            st.caption(f"❌ Exit code {res['returncode']} after {res['seconds']} s")
        if res["stdout"]:
            st.code(res["stdout"], language="text")
        if res["stderr"]:
            st.code(res["stderr"], language="text")
        for fig in res["figures"]:
            st.image(fig)
        for f in res["files"]:
            p = Path(f)
            st.download_button(f"⬇ {p.name}", p.read_bytes(), file_name=p.name, key=f"dl_{key}_{p.name}")

    st.markdown("---")
    st.markdown("### How the code works")
    st.markdown(c["overview"])
    with st.expander("Line-by-line explanation", expanded=True):
        lines = script.splitlines()
        for note in c.get("line_notes", []):
            st.markdown(f"**Lines {note['lines']}** — {note['explanation']}")
            try:
                a, _, b = str(note["lines"]).partition("-")
                a, b = int(a), int(b or a)
                snippet = "\n".join(lines[a - 1:b])
                if snippet.strip():
                    st.code(snippet, language="python")
            except ValueError:
                pass
    if c.get("expected_output"):
        st.markdown("**What you should see:** " + c["expected_output"])
    if c.get("try_next"):
        st.markdown("**Try changing:**\n" + "\n".join(f"- {t}" for t in c["try_next"]))
    if script.strip() != c["script"].strip():
        if st.button("🧠 Explain my edited version", key=f"explain_{key}"):
            with st.spinner("Explaining…"):
                c.update(code_generator.explain_code(script))
                c["script"] = script
                storage.save(lec)
            st.rerun()


def sources_tab(lec, sec):
    for i in sec["unit_ids"]:
        u = lec["units"][i]
        with st.expander(u["label"]):
            if u.get("slide_text"):
                st.markdown("**Slide text**")
                st.text(u["slide_text"])
            if u.get("image_desc"):
                st.markdown("**What the picture shows (AI)**")
                st.write(u["image_desc"])
            if u.get("speech"):
                st.markdown(f"**Lecturer ({fmt_time(u.get('start'))}–{fmt_time(u.get('end'))})**")
                st.write(u["speech"])


@st.fragment(run_every=2)
def progress_panel(lid: str, n_sections_shown: int):
    """Live progress for a lecture that is being generated (refreshes every 2 seconds)."""
    job = jobs.get(lid)
    if not job or not job.active:
        st.rerun()  # finished (or stopped): show the full page
        return
    with st.container(border=True):
        st.markdown("### ⏳ Generating notes…" if job.state == "running" else "### 🕒 Waiting in the queue…")
        st.progress(job.overall(), text=job.message)
        st.markdown(time_line(job))
        c1, c2 = st.columns([3, 1])
        with c1:
            if job.log:
                with st.expander("Steps so far"):
                    st.markdown("\n".join(f"- `{t}` {m}" for t, m in job.log))
        with c2:
            if st.button("✖ Cancel", key=f"cancel_{lid}", width="stretch"):
                jobs.cancel(lid)
        st.caption("You can open other lectures or close this tab. Generation keeps running "
                   "as long as the app itself (its terminal window) stays open.")
    lec = storage.load(lid)
    if lec and len(lec.get("sections", [])) != n_sections_shown:
        st.rerun()  # a new section is ready: show it


def lecture_page(lid):
    lec = storage.load(lid)
    if not lec:
        st.warning("Lecture not found.")
        ss.view = "new"
        return
    st.header(lec["title"])
    src = lec["sources"]
    bits = [f"Created {lec['created']}"]
    if src.get("pdf_name"):
        bits.append(f"📄 {src['pdf_name']}")
    if src.get("youtube_url"):
        bits.append(f"▶ [{src.get('youtube_title') or 'YouTube'}]({src['youtube_url']})")
    elif src.get("media_name"):
        bits.append(f"🎙 {src['media_name']}")
    if src.get("transcript_from"):
        bits.append(f"Transcript: {src['transcript_from']}")
    timing = lec.get("timing")
    if timing and lec.get("status") == "done":
        bits.append(f"⏱ Generated in {fmt_duration(timing['total'])}")
    st.caption(" · ".join(bits))

    state = lecture_state(lid, lec.get("status"))
    job = jobs.get(lid)
    if state in ("running", "queued"):
        progress_panel(lid, len(lec.get("sections", [])))
    elif job and job.state == "done" and not ss.get(f"seen_done_{lid}"):
        ss[f"seen_done_{lid}"] = True
        st.success(f"✅ Your notes are ready! Total time: **{fmt_duration((timing or {}).get('total'))}**")
        st.toast("Notes ready", icon="✅")
    elif state in ("stopped", "error"):
        n_done = len(lec.get("sections", []))
        n_plan = len(lec.get("outline") or []) or "?"
        with st.container(border=True):
            if state == "error":
                st.error("Generation stopped with an error: " + (lec.get("error") or (job and job.error) or ""))
            else:
                st.warning(f"⏸ Generation stopped before it finished ({n_done} of {n_plan} sections written). "
                           "This happens if it was cancelled or the app was closed.")
            if st.button("▶ Resume from where it stopped", key=f"resume_{lid}", type="primary"):
                jobs.resume(lid)
                st.rerun()

    if timing and timing.get("stages") and state == "done":
        with st.expander("⏱ Time taken for each step"):
            steps = [f"- {STAGE_NAMES[k]}: **{fmt_duration(v)}**"
                     for k, v in timing["stages"].items() if k in STAGE_NAMES]
            st.markdown("\n".join(steps) + f"\n\n**Total: {fmt_duration(timing['total'])}**")

    if not lec["sections"]:
        if state not in ("running", "queued"):
            st.info("No notes were made for this lecture yet.")
            if st.button("🗑 Delete"):
                storage.delete(lid)
                ss.view = "new"
                st.rerun()
        return

    nav, main = st.columns([1, 3], gap="large")
    with nav:
        st.markdown("**Sections**")
        titles = [f"{i + 1}. {s['title']}" for i, s in enumerate(lec["sections"])]
        idx = st.radio("Sections", range(len(titles)), format_func=lambda i: titles[i],
                       key=f"sec_{lid}", label_visibility="collapsed")
        st.markdown("---")
        folder_picker(lid)
        level = st.selectbox("Export with", ["long", "medium", "short"], key=f"explvl_{lid}")
        st.download_button("⬇ Markdown", storage.to_markdown(lec, level), file_name=f"{lid}.md",
                           width="stretch")
        st.download_button("⬇ HTML (open, then print to PDF)", storage.to_html(lec, level),
                           file_name=f"{lid}.html", mime="text/html", width="stretch")
        if lec.get("transcript"):
            st.download_button("⬇ Transcript", "\n".join(f"[{fmt_time(s['start'])}] {s['text']}"
                                                         for s in lec["transcript"]),
                               file_name=f"{lid}-transcript.txt", width="stretch")
        with st.popover("🗑 Delete lecture", width="stretch"):
            st.write("This removes the notes and files for good.")
            if st.button("Yes, delete", type="primary"):
                storage.delete(lid)
                ss.view = "new"
                st.rerun()

    with main:
        sec = lec["sections"][idx]
        st.subheader(sec["title"])
        t1, t2, t3, t4 = st.tabs(["📝 Notes", "❓ Exam questions", "🐍 Python Lab", "📜 Sources"])
        with t1:
            notes_tab(lec, sec)
        with t2:
            quiz_tab(lec, sec)
        with t3:
            code_tab(lec, sec)
        with t4:
            sources_tab(lec, sec)


# ---------------------------------------------------------------- main
sidebar()
if ss.view == "new":
    new_lecture_page()
else:
    lecture_page(ss.view)
