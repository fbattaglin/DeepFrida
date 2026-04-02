#!/usr/bin/env python3
"""
Benchmark runner — executes prompts against Ollama models,
measures TTFT, tok/s, memory pressure, and chain-of-thought metadata.

Part of the Module 7 benchmark harness.
Run via run_benchmark.py, not directly.
"""

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import requests
import polars as pl

# Allow running from ~/ai-lab/benchmark/ with the package one level up
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ollama_client import is_model_loaded, warmup
from ollama_client.config import OLLAMA_BASE
from prompts import Prompt


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class RunResult:
    # Identity
    run_id: str
    model: str
    prompt_id: str
    category: str
    timestamp: str

    # Timing
    ttft_ms: float        # time to first token (ms)
    total_ms: float       # wall-clock total generation time (ms)
    tok_per_sec: float    # tokens/second derived from Ollama eval_duration

    # Token counts
    prompt_tokens: int    # prompt_eval_count from Ollama
    output_tokens: int    # eval_count from Ollama

    # Chain-of-thought breakdown (DeepSeek R1)
    think_tokens: int     # word count inside <think>...</think>
    answer_tokens: int    # word count outside the think block

    # Full output
    output_text: str      # raw output including think block
    answer_text: str      # answer only (think stripped)

    # Quality signal
    output_too_short: bool  # True if output_tokens < prompt.expected_min_tokens

    # System
    ram_before_gb: float  # unified memory used before generation
    ram_after_gb: float   # unified memory used after generation
    cold_load: bool       # True if model was not resident before this run


# ── Memory helpers ────────────────────────────────────────────────────────────

def get_memory_gb() -> float:
    """
    Read current unified memory usage via vm_stat (macOS only).
    Returns sum of active + wired + compressed pages in GB.
    Returns -1.0 if vm_stat is unavailable.
    """
    try:
        out = subprocess.check_output(["vm_stat"], text=True)
        pages: dict[str, int] = {}
        for line in out.splitlines():
            if "Pages active" in line:
                pages["active"] = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages wired down" in line:
                pages["wired"] = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages occupied by compressor" in line:
                pages["compressed"] = int(line.split(":")[1].strip().rstrip("."))
        used = pages.get("active", 0) + pages.get("wired", 0) + pages.get("compressed", 0)
        return round(used * 4096 / 1e9, 2)
    except (subprocess.SubprocessError, ValueError, KeyError):
        return -1.0


# ── Core runner ───────────────────────────────────────────────────────────────

def run_prompt(model: str, prompt: Prompt, warm: bool = True) -> RunResult:
    """
    Execute a single prompt and return a fully populated RunResult.

    Args:
        model : Ollama model tag, e.g. "deepseek-r1:14b"
        prompt: Prompt dataclass from prompts.py
        warm  : if True, ensure model is loaded before measuring
                if False, measures cold-start (load + inference)
    """
    run_id = f"{model.replace(':', '_')}_{prompt.id}_{int(time.time())}"
    timestamp = datetime.now(timezone.utc).isoformat()

    if warm and not is_model_loaded(model):
        print(f"    [warmup] Loading {model}...", end=" ", flush=True)
        t = warmup(model)
        print(f"ready in {t}s")

    cold_load = not is_model_loaded(model)
    ram_before = get_memory_gb()

    payload = {
        "model": model,
        "prompt": prompt.text,
        "stream": True,
        "options": {
            "temperature": prompt.temperature,
            "seed": prompt.seed,
            "num_ctx": 4096,
        },
    }

    full_text = ""
    ttft_ms: float | None = None
    final_chunk: dict = {}
    t_start = time.perf_counter()

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
            tok = chunk.get("response", "")

            if ttft_ms is None and tok.strip():
                ttft_ms = (time.perf_counter() - t_start) * 1000

            full_text += tok

            if chunk.get("done"):
                final_chunk = chunk
                break

    total_ms = (time.perf_counter() - t_start) * 1000
    ram_after = get_memory_gb()

    # Parse chain-of-thought blocks (DeepSeek R1)
    think_match = re.search(r"<think>(.*?)</think>", full_text, re.DOTALL)
    think_text = think_match.group(1).strip() if think_match else ""
    answer_text = re.sub(r"<think>.*?</think>", "", full_text, flags=re.DOTALL).strip()

    # Token counts from Ollama's native stats (more accurate than counting ourselves)
    prompt_tokens = final_chunk.get("prompt_eval_count", 0)
    output_tokens = final_chunk.get("eval_count", 0)

    # Throughput from Ollama's eval_duration (nanoseconds)
    eval_ns = final_chunk.get("eval_duration", 1)
    tok_per_sec = round(output_tokens / (eval_ns / 1e9), 2) if eval_ns else 0.0

    return RunResult(
        run_id=run_id,
        model=model,
        prompt_id=prompt.id,
        category=prompt.category,
        timestamp=timestamp,
        ttft_ms=round(ttft_ms or 0.0, 1),
        total_ms=round(total_ms, 1),
        tok_per_sec=tok_per_sec,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        think_tokens=len(think_text.split()) if think_text else 0,
        answer_tokens=len(answer_text.split()),
        output_text=full_text,
        answer_text=answer_text,
        output_too_short=output_tokens < prompt.expected_min_tokens,
        ram_before_gb=ram_before,
        ram_after_gb=ram_after,
        cold_load=cold_load,
    )


# ── Suite runner ──────────────────────────────────────────────────────────────

def run_suite(
    models: list[str],
    prompts: list[Prompt],
    n_runs: int = 3,
    warm: bool = True,
    output_path: str = "results.jsonl",
) -> pl.DataFrame:
    """
    Run the full benchmark suite across all model/prompt combinations.

    Args:
        models      : list of Ollama model tags
        prompts     : list of Prompt objects from prompts.py
        n_runs      : repetitions per prompt (use >= 3 for variance data)
        warm        : pre-load models before measuring
        output_path : where to write raw JSONL results

    Returns:
        Polars DataFrame (without full output text — use the JSONL for that)
    """
    total = len(models) * len(prompts) * n_runs
    print(f"Benchmark: {len(models)} model(s) × {len(prompts)} prompt(s) × {n_runs} run(s) = {total} total")
    print(f"Output   : {output_path}\n")

    results: list[dict] = []

    with open(output_path, "w") as f:
        i = 0
        for model in models:
            print(f"── Model: {model}")
            for prompt in prompts:
                for run_n in range(n_runs):
                    i += 1
                    label = f"[{i}/{total}] {prompt.id} (run {run_n + 1}/{n_runs})"
                    print(f"  {label}", end="  ", flush=True)

                    result = run_prompt(model, prompt, warm=warm)

                    status = "⚠ SHORT" if result.output_too_short else "ok"
                    print(f"→ {result.tok_per_sec} tok/s | TTFT {result.ttft_ms}ms | {status}")

                    row = asdict(result)
                    f.write(json.dumps(row) + "\n")
                    results.append(row)

    # Build DataFrame without the large text columns
    df = pl.DataFrame(results).drop(["output_text", "answer_text"])
    return df
