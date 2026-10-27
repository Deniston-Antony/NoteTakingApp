"""Reads a lecture PDF: text and a picture of every page."""
from pathlib import Path
from typing import Callable

import pymupdf


def process_pdf(pdf_path: Path, assets_dir: Path,
                progress: Callable[[float], None] | None = None) -> list[dict]:
    """Returns one dict per page: {"page", "text", "image", "has_images"}.
    `image` is a file name inside assets_dir."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    slides = []
    with pymupdf.open(pdf_path) as doc:
        n = len(doc)
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            name = f"slide_{i + 1:03d}.png"
            page.get_pixmap(dpi=110).save(assets_dir / name)
            slides.append({
                "page": i + 1,
                "text": text,
                "image": name,
                "has_images": bool(page.get_images()),
            })
            if progress:
                progress((i + 1) / n)
    return slides
