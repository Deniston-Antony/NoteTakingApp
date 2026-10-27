"""End-to-end test: sample PDF + audio -> notes, questions, one Python script.
Run:  venv\\Scripts\\python.exe tests\\test_pipeline.py   (run make_samples.py first)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import code_generator, pipeline, transcriber  # noqa: E402

S = Path(__file__).parent / "samples"

t0 = time.time()
tr = transcriber.transcribe(S / "linear_regression.wav")
print(f"[transcribe] {time.time() - t0:.1f}s, {len(tr['segments'])} segments, lang={tr['language']}")
print("   ", " ".join(s["text"] for s in tr["segments"])[:200], "…")


def progress(stage, frac, msg):
    print(f"[{stage}] {frac:.0%} {msg}", flush=True)


t0 = time.time()
lec = pipeline.run(
    pipeline.Inputs(title="Linear Regression (test)", media_kind="audio",
                    media_bytes=(S / "linear_regression.wav").read_bytes(), media_name="linear_regression.wav",
                    pdf_bytes=(S / "linear_regression.pdf").read_bytes(), pdf_name="linear_regression.pdf"),
    pipeline.Options(describe_images=True, make_quiz=True, make_code=False),
    progress)
print(f"\npipeline: {time.time() - t0:.1f}s")

for u in lec["units"]:
    print(f"  {u['label']}: speech {u['start']}-{u['end']} :: {u['speech'][:70]!r}")
for s in lec["sections"]:
    n = s["notes"]
    print(f"\n== {s['title']} units={s['unit_ids']}")
    print("  short:", n["short"][:150])
    print("  long words:", len(n["long"].split()), "| images:", n["best_images"], "| refs:", [r["label"] for r in s["references"]])
    print("  quiz:", len(s["quiz"]["mcq"]), "mcq,", len(s["quiz"]["short_answer"]), "short,", len(s["quiz"]["long_answer"]), "long")

t0 = time.time()
code = code_generator.generate_code(lec["sections"][-1], lec["title"], run_name="test_code")
print(f"\n[code] {time.time() - t0:.1f}s verified={code['verified']} fixes={code['fix_log']}")
print(code["script"][:600])
