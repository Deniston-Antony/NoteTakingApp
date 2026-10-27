"""Estimates how long note generation will take, and corrects itself as steps finish."""
import time

# Rough seconds on an RTX 4070 + qwen3:14b. Only a starting guess: the estimate is
# scaled by how fast the finished steps actually ran on this PC.
WHISPER_SPEED = 42          # seconds of audio transcribed per second (measured: 41-52x)
WHISPER_LOAD = 10
VISION_PER_IMAGE = 2.5      # measured 2.4-2.6 s
VISION_LOAD = 5
ALIGN = 10
OUTLINE = 20
NOTES_PER_SECTION = 36     # measured 34-49 s
QUIZ_PER_SECTION = 33      # measured 26-42 s
CODE_PER_SECTION = 40
DOWNLOAD_GUESS = 30

STAGE_NAMES = {"download": "Download", "transcribe": "Speech to text", "pdf": "Reading PDF",
               "vision": "Looking at pictures", "align": "Matching speech to slides",
               "notes": "Writing notes", "extras": "Exam questions & code"}


def guess_sections(n_units: int) -> int:
    return 1 if n_units <= 2 else min(12, max(2, n_units // 2))  # matches the outline step


def fmt_duration(sec: float | None) -> str:
    if sec is None:
        return "–"
    sec = int(round(sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


class Estimator:
    def __init__(self):
        self.t0 = time.time()
        self.plan: dict[str, float] = {}      # stage -> estimated seconds
        self.started: dict[str, float] = {}   # stage -> start time
        self.finished: dict[str, float] = {}  # stage -> actual seconds
        self.current: str | None = None
        self.ready = False                    # False until every step can be estimated

    def set(self, stage: str, seconds: float) -> None:
        self.plan[stage] = max(float(seconds), 1.0)

    def drop(self, stage: str) -> None:
        self.plan.pop(stage, None)

    def enter(self, stage: str | None) -> None:
        if stage == self.current:
            return
        now = time.time()
        if self.current is not None:
            self.finished[self.current] = self.finished.get(self.current, 0) + now - self.started[self.current]
        self.current = stage
        if stage is not None:
            self.started[stage] = now

    def elapsed(self) -> float:
        return time.time() - self.t0

    def _speed_factor(self) -> float:
        est = sum(self.plan[s] for s in self.finished if s in self.plan)
        act = sum(self.finished[s] for s in self.finished if s in self.plan)
        return min(max(act / est, 0.4), 3.0) if est > 20 else 1.0

    def remaining(self, frac: float = 0.0) -> float | None:
        if not self.ready:
            return None
        factor = self._speed_factor()
        left = 0.0
        cur = self.current
        if cur in self.plan:
            spent = time.time() - self.started[cur]
            if frac >= 0.1 and spent > 5:  # enough progress inside this step to measure it directly
                total_cur = spent / frac
            else:
                total_cur = max(self.plan[cur] * factor, spent)
            left += max(total_cur - spent, 0)
        for s, sec in self.plan.items():
            if s not in self.finished and s != cur:
                left += sec * factor
        return left

    def summary(self) -> dict:
        self.enter(None)
        return {"total": round(self.elapsed(), 1),
                "stages": {s: round(v, 1) for s, v in self.finished.items()}}
