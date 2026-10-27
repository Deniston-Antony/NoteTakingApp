"""Matches pieces of the lecture recording to the slides they talk about."""
import numpy as np

from core import llm


def chunk_segments(segments: list[dict], max_seconds: float) -> list[dict]:
    """Joins transcript segments into chunks of about `max_seconds`."""
    chunks, cur = [], None
    for s in segments:
        if cur is None:
            cur = {"start": s["start"], "end": s["end"], "text": s["text"]}
        elif s["end"] - cur["start"] > max_seconds:
            chunks.append(cur)
            cur = {"start": s["start"], "end": s["end"], "text": s["text"]}
        else:
            cur["end"] = s["end"]
            cur["text"] += " " + s["text"]
    if cur:
        chunks.append(cur)
    return chunks


def _normalise(m: np.ndarray) -> np.ndarray:
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def align(chunks: list[dict], slides: list[dict], skip_penalty: float = 0.01) -> list[int]:
    """Returns the slide index for every chunk.
    Lectures mostly move forward through slides, so the match is forced to never go
    backwards (dynamic programming over a similarity matrix)."""
    if not chunks or not slides:
        return []
    slide_texts = [((s.get("text") or "") + " " + (s.get("image_desc") or "")).strip() for s in slides]
    n_c, n_s = len(chunks), len(slides)
    if not any(slide_texts):  # no text to match on: spread evenly over time
        return [min(int(i * n_s / n_c), n_s - 1) for i in range(n_c)]

    s_emb = _normalise(np.array(llm.embed(
        ["search_document: " + (t[:2000] or f"slide {i + 1}") for i, t in enumerate(slide_texts)])))
    c_emb = _normalise(np.array(llm.embed(["search_query: " + c["text"][:2000] for c in chunks])))
    sim = c_emb @ s_emb.T  # (chunks, slides)

    score = np.full((n_c, n_s), -np.inf)
    back = np.zeros((n_c, n_s), dtype=int)
    score[0] = sim[0] - skip_penalty * np.arange(n_s)
    for i in range(1, n_c):
        for k in range(n_s):
            prev = score[i - 1, :k + 1] - skip_penalty * np.maximum(k - np.arange(k + 1) - 1, 0)
            j = int(np.argmax(prev))
            score[i, k] = sim[i, k] + prev[j]
            back[i, k] = j
    path = [int(np.argmax(score[-1]))]
    for i in range(n_c - 1, 0, -1):
        path.append(back[i, path[-1]])
    return path[::-1]
