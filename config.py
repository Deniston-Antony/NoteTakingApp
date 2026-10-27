"""App settings. Change model names here to swap in other local models."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@dataclass
class Config:
    # Ollama (local AI runner) - all models run on this PC
    ollama_host: str = "http://127.0.0.1:11434"
    text_model: str = "qwen3:14b"          # notes, exam questions, Python scripts
    vision_model: str = "qwen2.5vl:7b"     # reads slide images and video frames
    embed_model: str = "nomic-embed-text"  # matches speech to slides
    text_model_thinking: bool = False      # True = slower but sometimes better answers
    num_ctx: int = 8192                    # tokens the model reads at once (8192 fits fully on a 12 GB GPU)
    max_answer_tokens: int = 3500          # longest answer the model may write (stops runaway answers)
    request_timeout: int = 600             # seconds before one AI request is abandoned

    # Speech to text (faster-whisper)
    whisper_model: str = "large-v3-turbo"
    whisper_dir: Path = ROOT / "models" / "whisper"

    # Storage
    data_dir: Path = ROOT / "data"

    # Processing
    segment_minutes: float = 4.0        # audio/video without slides: minutes per chunk
    align_chunk_seconds: float = 20.0   # audio + slides: size of speech pieces matched to slides
    max_section_chars: int = 16000      # max lecture text sent to the model for one section

    # Python Lab
    code_timeout: int = 30              # seconds before a running script is stopped
    code_fix_attempts: int = 2          # times the AI tries to fix a generated script that crashes


CFG = Config()
CFG.data_dir.mkdir(parents=True, exist_ok=True)
(CFG.data_dir / "lectures").mkdir(exist_ok=True)
(CFG.data_dir / "runs").mkdir(exist_ok=True)
