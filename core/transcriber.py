"""Speech to text with faster-whisper (runs locally, uses the GPU when available)."""
import gc
from typing import Callable

from config import CFG
from core import gpu


def _load_model(device: str):
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    try:  # use the downloaded copy, no internet
        return WhisperModel(CFG.whisper_model, device=device, compute_type=compute,
                            download_root=str(CFG.whisper_dir), local_files_only=True)
    except Exception:  # first run only: download the model
        return WhisperModel(CFG.whisper_model, device=device, compute_type=compute,
                            download_root=str(CFG.whisper_dir))


def download_model() -> None:
    gpu.setup_cuda()
    _load_model("cpu")


def _run(path, language, progress, device):
    model = _load_model(device)
    try:
        segments, info = model.transcribe(str(path), language=language, vad_filter=True, beam_size=5)
        out = []
        for s in segments:
            text = s.text.strip()
            if text:
                out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
            if progress and info.duration:
                progress(min(s.end / info.duration, 1.0))
        return {"language": info.language, "duration": info.duration, "segments": out}
    finally:
        del model
        gc.collect()


def transcribe(path, language: str | None = None,
               progress: Callable[[float], None] | None = None) -> dict:
    """Returns {"language", "duration", "segments": [{"start", "end", "text"}]}."""
    gpu.setup_cuda()
    if gpu.cuda_available():
        try:
            return _run(path, language, progress, "cuda")
        except RuntimeError as e:
            if "cuda" not in str(e).lower() and "cudnn" not in str(e).lower() and "cublas" not in str(e).lower():
                raise
    return _run(path, language, progress, "cpu")
