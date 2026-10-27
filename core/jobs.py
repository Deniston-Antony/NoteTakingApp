"""Background jobs: note generation runs in its own thread, so it keeps going while you
browse other pages (or close the browser tab). Only one job uses the GPU at a time;
others wait in a queue. Jobs stop if the app itself (the terminal running Streamlit) is closed;
those lectures can be continued with Resume."""
import threading
import time
from dataclasses import dataclass, field

from core import pipeline, storage


@dataclass
class Job:
    lecture_id: str
    title: str
    state: str = "queued"          # queued | running | done | error | cancelled
    stage: str = ""
    frac: float = 0.0
    message: str = "Waiting for the lecture before this one to finish…"
    elapsed: float = 0.0           # seconds, as of `updated`
    left: float | None = None      # estimated seconds left, as of `updated`
    updated: float = field(default_factory=time.time)
    log: list = field(default_factory=list)      # [(clock time, message)] one per step
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    @property
    def active(self) -> bool:
        return self.state in ("queued", "running")

    def live_elapsed(self) -> float:
        return self.elapsed + (time.time() - self.updated if self.state == "running" else 0)

    def live_left(self) -> float | None:
        if self.left is None:
            return None
        return max(self.left - (time.time() - self.updated), 0)

    def overall(self) -> float:
        """Fraction of the whole job done (0-1), from the time estimate."""
        left, el = self.live_left(), self.live_elapsed()
        if left is None or el + left <= 0:
            return 0.0
        return min(el / (el + left), 0.99)


_jobs: dict[str, Job] = {}
_gpu = threading.Lock()


def _work(job: Job, inp: pipeline.Inputs, opt: pipeline.Options, lec: dict):
    with _gpu:  # one lecture at a time on the GPU
        if job.cancel.is_set():
            job.state = "cancelled"
            lec["status"] = "stopped"
            storage.save(lec)
            return
        job.state = "running"
        job.updated = time.time()

        def progress(stage, frac, msg):
            if stage != job.stage:
                job.log.append((time.strftime("%H:%M:%S"), msg))
            job.stage, job.frac, job.message = stage, frac, msg

        def on_time(elapsed, left):
            job.elapsed, job.left, job.updated = elapsed, left, time.time()

        try:
            pipeline.run(inp, opt, progress, on_time, lec=lec, cancel=job.cancel)
            job.state = "done"
        except pipeline.Cancelled:
            job.state = "cancelled"
        except Exception as e:
            job.state = "error"
            job.error = f"{type(e).__name__}: {e}"
        job.left = 0 if job.state == "done" else None
        job.updated = time.time()


def _launch(lec: dict, inp, opt) -> str:
    job = Job(lec["id"], lec["title"])
    _jobs[lec["id"]] = job
    threading.Thread(target=_work, args=(job, inp, opt, lec), daemon=True, name=f"job-{lec['id']}").start()
    return lec["id"]


def start(inp: pipeline.Inputs, opt: pipeline.Options) -> str:
    """Starts a new lecture in the background. Returns its id straight away."""
    lec = storage.new_lecture(inp.title or "Untitled lecture")
    storage.save(lec)
    return _launch(lec, inp, opt)


def resume(lid: str) -> str:
    """Continues a lecture that stopped (or failed) from where it got to."""
    lec = storage.load(lid)
    opt = pipeline.Options(**{k: v for k, v in (lec.get("options") or {}).items()
                              if k in pipeline.Options.__dataclass_fields__})
    inp = pipeline.inputs_from_saved(lec)
    return _launch(lec, inp, opt)


def get(lid: str) -> Job | None:
    return _jobs.get(lid)


def is_active(lid: str) -> bool:
    j = _jobs.get(lid)
    return bool(j and j.active)


def active() -> list[Job]:
    return [j for j in _jobs.values() if j.active]


def cancel(lid: str) -> None:
    j = _jobs.get(lid)
    if j:
        j.cancel.set()
        j.message = "Cancelling… (stops after the current step)"
