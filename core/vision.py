"""Describes slide images and video frames with the local vision model."""
from pathlib import Path

from config import CFG
from core import llm

PROMPT = (
    "You are helping a student take notes. Describe this {kind} from a lecture. "
    "Mention diagrams, charts, tables, equations or code it shows, and copy any important text. "
    "Be factual and concise (under 120 words). Do not add an introduction."
)


def describe(image_path: Path, kind: str = "lecture slide") -> str:
    return llm.chat(PROMPT.format(kind=kind), model=CFG.vision_model,
                    images=[image_path], temperature=0.1, num_ctx=8192)
