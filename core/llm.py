"""Talks to the local Ollama server. Nothing here uses the internet."""
import json
import re

import httpx
import ollama

from config import CFG
from core.mathfix import fix_obj

# timeout: give up on a single request after this many seconds (stops endless generations)
_client = ollama.Client(host=CFG.ollama_host, timeout=CFG.request_timeout)


class LLMError(RuntimeError):
    pass


def is_running() -> bool:
    try:
        _client.list()
        return True
    except Exception:
        return False


def installed_models() -> set[str]:
    try:
        names = {m.model for m in _client.list().models}
    except Exception:
        return set()
    # "qwen3:14b" and "nomic-embed-text:latest" style names
    return names | {n.removesuffix(":latest") for n in names}


def missing_models() -> list[str]:
    have = installed_models()
    return [m for m in (CFG.text_model, CFG.vision_model, CFG.embed_model) if m not in have]


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def chat(prompt: str, system: str | None = None, model: str | None = None,
         images: list | None = None, schema: dict | None = None,
         temperature: float = 0.3, num_ctx: int | None = None, max_tokens: int | None = None,
         think: bool | None = None) -> str:
    """think=True lets the text model reason step by step first (slower, better for hard problems)."""
    model = model or CFG.text_model
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    user = {"role": "user", "content": prompt}
    if images:
        user["images"] = [str(p) for p in images]
    messages.append(user)

    kwargs = dict(model=model, messages=messages,
                  options={"temperature": temperature, "num_ctx": num_ctx or CFG.num_ctx,
                           # hard cap on answer length, and a penalty that discourages repeating loops
                           "num_predict": max_tokens or CFG.max_answer_tokens, "repeat_penalty": 1.1})
    if schema:
        kwargs["format"] = schema
    if model == CFG.text_model:
        kwargs["think"] = CFG.text_model_thinking if think is None else think
    try:
        resp = _client.chat(**kwargs)
    except ollama.ResponseError as e:
        raise LLMError(f"Ollama error with model '{model}': {e.error}") from e
    except httpx.TimeoutException as e:
        raise LLMError(f"The model '{model}' took longer than {CFG.request_timeout}s to answer.") from e
    except Exception as e:
        raise LLMError(f"Could not reach Ollama at {CFG.ollama_host}. Is the Ollama app running? ({e})") from e
    return _strip_think(resp.message.content or "")


def chat_json(prompt: str, schema: dict, **kw) -> dict:
    """Ask for JSON that matches `schema`. Retries once if the reply can't be parsed."""
    last = ""
    for attempt in range(2):
        p = prompt if attempt == 0 else prompt + "\n\nReturn ONLY valid JSON matching the schema."
        last = chat(p, schema=schema, **kw)
        try:
            return fix_obj(json.loads(last))  # repair LaTeX damaged by JSON escapes
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", last, flags=re.S)
            if m:
                try:
                    return fix_obj(json.loads(m.group(0)))
                except json.JSONDecodeError:
                    pass
    raise LLMError("The model did not return valid JSON:\n" + last[:500])


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        return list(_client.embed(model=CFG.embed_model, input=texts).embeddings)
    except Exception as e:
        raise LLMError(f"Embedding failed ({CFG.embed_model}): {e}") from e


def unload(model: str) -> None:
    """Free GPU memory used by a model."""
    try:
        loaded = {m.model for m in _client.ps().models}
        if model not in loaded and f"{model}:latest" not in loaded:
            return  # not in memory: nothing to do (and don't load it by accident)
        _client.generate(model=model, prompt="", keep_alive=0)
    except Exception:
        pass
