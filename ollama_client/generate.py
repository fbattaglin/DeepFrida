import json
import re
import time
from typing import Iterator

import requests

from .config import OLLAMA_BASE, DEFAULT_MODEL


def stream_generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    **options,
) -> Iterator[str]:
    """Yields one token string at a time as they arrive from Ollama."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": options,
    }
    try:
        with requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                chunk = json.loads(raw_line)
                yield chunk["response"]
                if chunk.get("done"):
                    return
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_BASE}. Is it running?")
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama stream timed out.")


def generate_with_stats(
    prompt: str,
    model: str = DEFAULT_MODEL,
    **options,
) -> dict:
    """
    Runs a prompt and returns think block, answer, and timing metrics.

    Returns:
        think       : text inside <think>...</think>
        answer      : text after </think>
        ttft_ms     : time to first token (ms)
        tok_per_sec : generation speed
        total_tokens: eval_count from Ollama
        elapsed_s   : wall-clock total time
    """
    full_text = ""
    t_start = time.perf_counter()
    ttft = None
    final_chunk = {}

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": options,
    }

    try:
        with requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            stream=True,
            timeout=300,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                chunk = json.loads(raw_line)
                tok = chunk["response"]
                if ttft is None and tok.strip():
                    ttft = (time.perf_counter() - t_start) * 1000
                full_text += tok
                print(tok, end="", flush=True)
                if chunk.get("done"):
                    final_chunk = chunk
                    break
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_BASE}. Is it running?")
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama generation timed out.")

    elapsed = time.perf_counter() - t_start
    think_match = re.search(r"<think>(.*?)</think>", full_text, re.DOTALL)
    think = think_match.group(1).strip() if think_match else ""
    answer = re.sub(r"<think>.*?</think>", "", full_text, flags=re.DOTALL).strip()
    total_tokens = final_chunk.get("eval_count", 0)

    return {
        "think": think,
        "answer": answer,
        "ttft_ms": round(ttft or 0),
        "tok_per_sec": round(total_tokens / elapsed, 1) if elapsed > 0 else 0,
        "total_tokens": total_tokens,
        "elapsed_s": round(elapsed, 2),
    }
