"""Makes the NVIDIA CUDA libraries (installed as pip packages) visible to Whisper on Windows."""
import os
import site
from pathlib import Path

_done = False


def setup_cuda() -> None:
    global _done
    if _done or os.name != "nt":
        return
    _done = True
    for sp in site.getsitepackages():
        base = Path(sp) / "nvidia"
        if not base.is_dir():
            continue
        for bin_dir in base.glob("*/bin"):
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                pass
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False
