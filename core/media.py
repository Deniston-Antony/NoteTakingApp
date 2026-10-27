"""Video helpers: grab still frames (uses PyAV, which comes with faster-whisper)."""
from pathlib import Path

import av


def has_video(path: Path) -> bool:
    try:
        with av.open(str(path)) as c:
            return len(c.streams.video) > 0
    except Exception:
        return False


def duration(path: Path) -> float | None:
    """Length of an audio/video file in seconds (None if unknown)."""
    try:
        with av.open(str(path)) as c:
            if c.duration:
                return c.duration / 1_000_000
            s = (c.streams.audio or c.streams.video)[0]
            return float(s.duration * s.time_base) if s.duration else None
    except Exception:
        return None


def extract_frame(video_path: Path, seconds: float, out_path: Path, max_size: int = 960) -> bool:
    """Saves the frame at about `seconds` as a JPEG. Returns False if it fails."""
    try:
        with av.open(str(video_path)) as c:
            stream = c.streams.video[0]
            if stream.time_base:
                c.seek(int(seconds / stream.time_base), stream=stream, any_frame=False, backward=True)
            for frame in c.decode(stream):
                if frame.time is not None and frame.time < seconds - 2:
                    continue  # skip ahead from the keyframe
                img = frame.to_image()
                img.thumbnail((max_size, max_size))
                img.convert("RGB").save(out_path, "JPEG", quality=85)
                return True
    except Exception:
        pass
    return False
