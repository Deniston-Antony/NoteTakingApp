"""YouTube: download the video (needs internet) and get captions if the video has them.
Everything after the download runs offline."""
import re
from pathlib import Path

_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")


def video_id(url: str) -> str | None:
    m = _ID_RE.search(url)
    if m:
        return m.group(1)
    url = url.strip()
    return url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url) else None


def fetch_captions(vid: str) -> list[dict] | None:
    """Returns segments [{"start", "end", "text"}] or None if no captions."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(vid, languages=["en", "en-US", "en-GB"])
        except Exception:
            transcripts = list(api.list(vid))
            if not transcripts:
                return None
            fetched = transcripts[0].fetch()
        out = []
        for s in fetched:
            text = s.text.replace("\n", " ").strip()
            if text:
                out.append({"start": round(s.start, 2), "end": round(s.start + s.duration, 2), "text": text})
        return out or None
    except Exception:
        return None


def _fetch(url: str, out_dir: Path, name: str, formats: list[str], tries: int = 3):
    """Downloads one stream. YouTube sometimes refuses a request (HTTP 403), so this
    retries and falls back to other formats."""
    import time

    import yt_dlp
    last_err = None
    for attempt in range(tries):
        fmt = formats[min(attempt, len(formats) - 1)]
        for old in out_dir.glob(f"{name}.*"):  # remove half-downloaded files
            old.unlink(missing_ok=True)
        opts = {"format": fmt, "outtmpl": str(out_dir / f"{name}.%(ext)s"), "quiet": True,
                "no_warnings": True, "noprogress": True, "noplaylist": True,
                "retries": 5, "fragment_retries": 5, "http_chunk_size": 10 * 1024 * 1024}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
            if path.exists() and path.stat().st_size > 0:
                return path, info
            last_err = RuntimeError(f"{name} download produced no file")
        except Exception as e:
            last_err = e
        time.sleep(2 * (attempt + 1))
    raise last_err


def download(url: str, out_dir: Path, want_video: bool = True) -> tuple[Path, Path | None, dict]:
    """Downloads the audio, and a low-resolution video for frames, as separate files
    (YouTube serves them separately; keeping them apart means ffmpeg merging isn't needed).
    Returns (audio_path, video_path or None, meta)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    audio, info = _fetch(url, out_dir, "audio",
                         ["bestaudio[ext=m4a]/bestaudio/best", "bestaudio/best", "worstaudio/worst"])
    video = None
    if want_video:
        try:
            video, _ = _fetch(url, out_dir, "video", [
                "bestvideo[height<=480][vcodec^=avc1]/bestvideo[height<=480]/best[height<=480]/worst",
                "bestvideo[height<=360]/worstvideo/worst",
                "worstvideo/worst"])
        except Exception:
            video = None  # notes still work without frames
    meta = {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),
        "url": info.get("webpage_url") or url,
        "id": info.get("id"),
    }
    return audio, video, meta
