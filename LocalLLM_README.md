# Module 4 — Ollama REST API & Python Client

> **Lab environment:** Mac Mini M4 Pro · 24 GB unified memory · Ollama 0.18.2 · Python 3.12

---

## Table of Contents

1. [What This Module Is About](#1-what-this-module-is-about)
2. [Why Build a Client Instead of Using Ollama's CLI?](#2-why-build-a-client-instead-of-using-ollamas-cli)
3. [How Ollama Works Under the Hood](#3-how-ollama-works-under-the-hood)
4. [The REST API Surface](#4-the-rest-api-surface)
5. [Understanding the Streaming Protocol (NDJSON)](#5-understanding-the-streaming-protocol-ndjson)
6. [Project Structure](#6-project-structure)
7. [The `ollama_client` Package — Layer by Layer](#7-the-ollama_client-package--layer-by-layer)
   - [Layer 0 — config.py](#layer-0--configpy)
   - [Layer 1 — generate.py](#layer-1--generatepy)
   - [Layer 2 — chat.py](#layer-2--chatpy)
   - [Layer 3 — models.py](#layer-3--modelspy)
   - [Layer 4 — __init__.py](#layer-4--initpy)
8. [The REPL — repl.py](#8-the-repl--replpy)
9. [Key Concepts and Gotchas](#9-key-concepts-and-gotchas)
10. [Exercises](#10-exercises)
11. [Connection to the Rest of the Curriculum](#11-connection-to-the-rest-of-the-curriculum)

---

## 1. What This Module Is About

In Module 3 we ran DeepSeek R1 14B interactively using `ollama run` from the terminal. That works for experimentation, but it is a dead end for any real engineering work. You cannot:

- Measure time-to-first-token or tokens/second
- Separate the chain-of-thought `<think>` block from the final answer
- Chain calls together (output of one prompt becomes input of the next)
- Build pipelines, agents, or RAG workflows
- Integrate LLM output into your existing Python data stack (polars, duckdb, etc.)

Module 4 fixes all of this. We build a proper Python client for the Ollama REST API — a structured, reusable library that becomes the foundation for everything else in the curriculum: the benchmark harness (Module 7), RAG pipelines (Phase 2), and eventually agentic workflows.

By the end of this module you will have:

- A working mental model of how Ollama serves models over HTTP
- A four-layer Python package (`ollama_client`) you will reuse throughout the lab
- An interactive REPL (`repl.py`) with model switching, stats, and system prompt management
- Full understanding of NDJSON streaming and why it matters for latency measurement
- The ability to programmatically control every aspect of inference — model, parameters, context, parsing

---

## 2. Why Build a Client Instead of Using Ollama's CLI?

The `ollama run` command is a convenience wrapper. Under the hood, it does exactly what our Python client does — it sends HTTP requests to a local daemon. But the CLI hides everything interesting:

**What `ollama run` gives you:**
- Interactive chat in the terminal
- Automatic model downloading if not present
- Basic streaming output

**What it hides from you:**
- Token timing (TTFT, generation speed)
- The raw token stream (you see the assembled response, not individual tokens)
- Metadata from the final chunk (`eval_count`, `eval_duration`, `prompt_eval_count`)
- Any ability to parse or transform the output before displaying it
- The distinction between the `<think>` scratchpad and the final answer

When you call the REST API directly, you get all of this. Every token arrives as a separate JSON object. The final object in the stream contains detailed timing statistics from the model server itself. You can intercept the stream, parse it, route it, transform it, or feed it into another system — the full engineering surface is open.

This is the difference between using a tool and understanding it well enough to build on top of it.

---

## 3. How Ollama Works Under the Hood

Before touching any code, it helps to have the right mental model of what Ollama actually is.

### The Process Architecture

When you run `ollama serve` (or when it starts automatically as a Homebrew service), two processes appear:

```
ollama                    ← HTTP daemon, listens on localhost:11434
ollama_llama_server       ← the actual inference engine (llama.cpp + Metal)
```

The `ollama` process is essentially a model manager and HTTP router. It handles requests, manages model loading/unloading, and maintains a keep-alive timer. When you send an inference request, it delegates to `ollama_llama_server`, which runs the actual computation on the M4 Pro's GPU cores via Apple's Metal Performance Shaders.

### The Model Loading Lifecycle

```
First request for a model
    → ollama checks if model is in memory (GET /api/ps)
    → if not: mmap() the GGUF file into unified memory address space
    → pages load on demand as inference touches different weight layers
    → generation begins (you see tokens appearing)
    → after 5 minutes of idle: model is unloaded from memory
    → GGUF file remains on disk at ~/.ollama/models/blobs/
```

The `mmap()` call is important: Ollama does not read the entire 9 GB GGUF file into memory upfront. The OS maps the file's address space and pages in only the weight tensors that inference actually touches, on demand. This is why Activity Monitor shows `ollama_llama_server`'s memory footprint growing progressively during the first few inferences, then stabilising.

### Why This Matters for Your Client

Because model loading is a one-time cost per session, your client should:

1. **Warmup before benchmarking** — measure load time separately from inference time
2. **Check `GET /api/ps`** before sending a request — if the model is already loaded, you skip the 5–10 second load
3. **Not assume the model is always in memory** — if the keep-alive timer expires between calls, the next call pays the load cost again

---

## 4. The REST API Surface

Ollama exposes a small, clean HTTP API. These are the endpoints that matter for this module:

| Method | Endpoint | What it does |
|--------|----------|--------------|
| `POST` | `/api/generate` | Single-turn generation with a raw prompt string |
| `POST` | `/api/chat` | Multi-turn generation with a messages array |
| `GET` | `/api/tags` | List all downloaded models on disk |
| `GET` | `/api/ps` | List models currently loaded in memory |
| `POST` | `/api/show` | Architecture metadata for a specific model |
| `POST` | `/api/pull` | Download a model (streams progress events) |
| `DELETE` | `/api/delete` | Remove a model from disk |

### `/api/generate` vs `/api/chat` — The Key Distinction

This trips up most people. Both endpoints do the same underlying inference. The difference is how they handle the prompt:

**`/api/generate`** — you provide a raw `prompt` string. You are responsible for formatting. The model receives exactly the text you send, with no additional structure.

```json
{
  "model": "deepseek-r1:14b",
  "prompt": "What is the capital of France?",
  "stream": true
}
```

**`/api/chat`** — you provide a `messages` array (same format as OpenAI's API). Ollama internally formats this array into the chat template that the model was trained with. For DeepSeek R1, that template wraps messages in special tokens like `<|im_start|>user` and `<|im_end|>`. You never see these tokens — Ollama handles the conversion.

```json
{
  "model": "deepseek-r1:14b",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"}
  ],
  "stream": true
}
```

**When to use which:**

- Use `/api/generate` for: benchmarking (full control over prompt format), scripting, pipelines, any case where you want reproducible, explicit prompt construction
- Use `/api/chat` for: multi-turn conversations, interactive use, any case where the model's chat template matters for quality

For the benchmark harness in Module 7, we use `/api/generate` — it gives us exact control and makes runs reproducible. For the REPL and conversational use, we use `/api/chat` — it handles the message formatting correctly.

---

## 5. Understanding the Streaming Protocol (NDJSON)

This is the most important technical detail to understand before writing the client.

When you set `"stream": true`, Ollama sends back a **newline-delimited JSON** (NDJSON) stream. This means the HTTP response body is a sequence of complete JSON objects, one per line, arriving over time:

```
{"model":"deepseek-r1:14b","created_at":"2024-...","response":"The","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":" capital","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":" of","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":" France","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":" is","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":" Paris","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":".","done":false}
{"model":"deepseek-r1:14b","created_at":"2024-...","response":"","done":true,
 "eval_count":7,"eval_duration":183000000,"prompt_eval_count":12,...}
```

Key observations:

1. **Every line is a complete, valid JSON object.** No partial JSON, no buffering needed.
2. **`"response"` contains the new token** (or a small group of tokens) for that chunk.
3. **`"done": false`** on all chunks except the last.
4. **The final chunk** (`"done": true`) has an empty `"response"` and carries the statistics:
   - `eval_count` — number of tokens generated
   - `eval_duration` — generation time in nanoseconds
   - `prompt_eval_count` — number of tokens in the prompt
   - `prompt_eval_duration` — time spent processing the prompt (the prefill phase)
   - `total_duration` — wall-clock total time including model load

### Why Streaming Matters for TTFT Measurement

If you used `"stream": false`, the HTTP response would be a single JSON object that arrives only when generation is complete. You could measure total time, but not time-to-first-token (TTFT).

With `"stream": true`, you receive the first chunk as soon as the model produces its first token. The gap between sending the request and receiving that first chunk is your true TTFT. This is what Module 7's benchmark harness measures.

```python
t_start = time.perf_counter()

with requests.post(url, json=payload, stream=True) as resp:
    for raw_line in resp.iter_lines():
        chunk = json.loads(raw_line)
        tok = chunk["response"]

        if ttft is None and tok.strip():      # first non-whitespace token
            ttft = time.perf_counter() - t_start   # ← this is your TTFT

        # ... rest of the stream
```

For DeepSeek R1 14B on M4 Pro with a warm model, expect TTFT of 25–60ms. The prefill phase (processing the prompt tokens) happens before the first generation token — for a short prompt this is fast. For a long prompt (hundreds of tokens), TTFT can be several hundred milliseconds even with a warm model.

---

## 6. Project Structure

```
~/ai-lab/
│
├── ollama_client/              ← Python package (this module)
│   ├── __init__.py             ← public API exports
│   ├── config.py               ← OLLAMA_BASE, defaults
│   ├── generate.py             ← stream_generate, generate_with_stats
│   ← chat.py                  ← ChatSession class
│   └── models.py               ← list_models, is_model_loaded, warmup
│
├── repl.py                     ← interactive REPL (uses ollama_client)
├── observe_cot.py              ← chain-of-thought timing script (Module 3)
│
├── benchmark/                  ← Module 7 benchmark harness
│   ├── prompts.py
│   ├── runner.py               ← uses ollama_client package
│   ├── analyze.py
│   └── run_benchmark.py
│
└── notebooks/
    └── module4_experiments.ipynb
```

The `ollama_client` directory is a Python **package** — a directory containing an `__init__.py` file. This means you can import from it like any installed library:

```python
from ollama_client import stream_generate, ChatSession
```

Python finds it because you run scripts from `~/ai-lab/`, which is the package's parent directory. No installation required — the directory layout is enough.

---

## 7. The `ollama_client` Package — Layer by Layer

The package is designed in layers, each building on the previous. Understanding why each layer exists is more important than memorising the code.

---

### Layer 0 — `config.py`

```python
OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "deepseek-r1:14b"
DEFAULT_OPTIONS = {
    "temperature": 0.6,
    "num_ctx": 4096,
}
```

**Why a separate config file?**

Every other module imports from `config.py`. This means there is exactly one place to change the Ollama URL or default model. If you later run Ollama on a different port, or on a remote machine over a local network, you change one line and the entire package updates.

This is the **single source of truth** principle — a basic but important engineering practice that becomes painful to retrofit when a project grows.

---

### Layer 1 — `generate.py`

This file contains two functions: `stream_generate` and `generate_with_stats`.

#### `stream_generate` — the foundation

```python
def stream_generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    **options,
) -> Iterator[str]:
```

This is a Python **generator function** — it uses `yield` instead of `return`. The key property of a generator: it produces values lazily, one at a time, only when the caller asks for the next one.

This maps perfectly onto the NDJSON stream. The function holds the HTTP connection open, reads one line at a time from the response body, parses the JSON, and yields the `"response"` field. The caller's loop receives one token per iteration, exactly as the model produces it.

```python
# Caller perspective — tokens arrive one at a time
for tok in stream_generate("Explain the KV cache"):
    print(tok, end="", flush=True)   # print immediately, no buffering
```

**Why `**options`?**

The function accepts any keyword arguments and passes them directly to Ollama's `"options"` field. This means you can pass any inference parameter without modifying the function signature:

```python
stream_generate("Hello", temperature=0.2, top_p=0.9, num_ctx=2048)
```

This design is intentionally flexible. As you explore more parameters in Module 5, you don't need to update the function — just pass new keyword arguments.

#### `generate_with_stats` — structured output

```python
def generate_with_stats(prompt: str, model: str = DEFAULT_MODEL, **options) -> dict:
```

This function wraps `stream_generate`'s logic to do three things simultaneously:

1. **Print tokens to stdout** as they arrive (so you see the output streaming live)
2. **Measure TTFT** precisely — the moment the first non-whitespace token arrives
3. **Parse the DeepSeek R1 chain-of-thought** — separate `<think>...</think>` from the final answer

The return value is a structured dict:

```python
{
    "think": "Let me work through this step by step...",  # scratchpad content
    "answer": "The answer is 42.",                         # final answer only
    "ttft_ms": 38,                                         # ms to first token
    "tok_per_sec": 36.4,                                   # generation speed
    "total_tokens": 187,                                   # tokens generated
    "elapsed_s": 5.13,                                     # wall-clock total
}
```

**Why separate `think` from `answer`?**

For programmatic use, the `<think>` block is noise. If you're building a pipeline where the model's answer needs to be parsed or used downstream, you want just the answer. But for analysis — understanding how much reasoning the model did, comparing think-token counts across task types — the think block is signal. Separating them gives you both.

The regex used for parsing:

```python
think_match = re.search(r"<think>(.*?)</think>", full_text, re.DOTALL)
```

`re.DOTALL` makes the `.` match newlines as well — essential because the think block spans multiple lines.

---

### Layer 2 — `chat.py`

```python
@dataclass
class ChatSession:
    model: str = DEFAULT_MODEL
    system: str = ""
    history: list[dict] = field(default_factory=list)
    options: dict = field(default_factory=lambda: dict(DEFAULT_OPTIONS))
```

`ChatSession` is a stateful wrapper around `/api/chat`. The critical design decision: **Ollama is stateless between requests**. It has no memory of previous messages. Every time you call `/api/chat`, you must send the entire conversation history from the beginning.

`ChatSession` maintains that history on the Python side and sends it with every request:

```
Turn 1: send [user_message_1]
Turn 2: send [user_message_1, assistant_reply_1, user_message_2]
Turn 3: send [user_message_1, assistant_reply_1, user_message_2, assistant_reply_2, user_message_3]
```

This has an important consequence: **the conversation grows with every turn**. After 10 exchanges, you're sending 20 messages on every request. The prefill phase (processing all that prior context) gets progressively slower. The `approx_tokens` property gives you a rough estimate of how much context budget you've consumed.

**The `system` prompt behaviour:**

If `session.system` is set, it's prepended to the messages array on every request. It does not count as a "turn" and is not stored in `history`. This means you can change the system prompt at any time — `session.system = "..."` — and the new prompt takes effect on the next call, while history is preserved.

When you call `session.reset()`, only `history` is cleared. The system prompt remains. This matches the expected UX: starting a new conversation topic while keeping the assistant's persona.

**The `@dataclass` decorator:**

Using `@dataclass` instead of a regular class gives us `__init__`, `__repr__`, and clean field defaults for free, without boilerplate. The `field(default_factory=...)` pattern is necessary for mutable defaults (lists and dicts) — Python's default argument gotcha means you cannot write `history: list = []` directly in a dataclass.

---

### Layer 3 — `models.py`

Four operational helpers:

#### `list_models()`

Calls `GET /api/tags`. Returns a list of dicts, one per downloaded model. Each dict contains `name`, `size`, `modified_at`, and digest. Useful for verifying what's available before a benchmark run.

#### `is_model_loaded(model: str) -> bool`

Calls `GET /api/ps` (process status). Returns `True` if the model is currently resident in unified memory, `False` if it's only on disk. The implementation strips the tag (`"deepseek-r1:14b"` → `"deepseek-r1"`) to handle tag variations gracefully.

This is the function that lets your benchmark harness distinguish between cold-start latency (loading + inference) and warm inference latency (inference only).

#### `model_info(model: str) -> dict`

Calls `POST /api/show`. Returns the model's architecture metadata — number of layers, attention heads, context length, quantization method, and more. Useful for understanding what you're actually running.

#### `warmup(model: str) -> float`

Forces the model into unified memory by sending a minimal request (a single space as the prompt, `stream=False`). Returns the load time in seconds. Call this before benchmarking to separate the cold-load cost from the inference measurement.

The implementation sends `"prompt": " "` rather than an empty string because some versions of Ollama skip processing on truly empty prompts.

---

### Layer 4 — `__init__.py`

```python
from .generate import stream_generate, generate_with_stats
from .chat import ChatSession
from .models import list_models, is_model_loaded, model_info, warmup
from .config import OLLAMA_BASE, DEFAULT_MODEL
```

The `__init__.py` is the **public API declaration** of the package. It controls what users of the package see when they write `from ollama_client import ...`.

The dot notation (`.generate`, `.chat`) means "import from the sibling module within this package." This is a relative import — it works regardless of where the package lives on the filesystem.

`__all__` lists the names that should be exported when someone writes `from ollama_client import *`. Even if you never use star imports, defining `__all__` is good practice — it makes the public API explicit and readable at a glance.

---

## 8. The REPL — `repl.py`

The REPL (Read-Eval-Print Loop) is the interactive frontend for the `ollama_client` package. It wraps `ChatSession` with a command system and CLI argument parsing.

### Running It

```bash
cd ~/ai-lab
source .venv/bin/activate

# Default: deepseek-r1:14b, temperature=0.6, ctx=4096
python repl.py

# Focused reasoning: lower temperature for precision
python repl.py --model deepseek-r1:14b --temperature 0.6

# Short context for fast responses
python repl.py --ctx 2048
```

### Commands

| Command | What it does |
|---------|-------------|
| `/reset` | Clear conversation history, keep system prompt |
| `/stats` | Show turn count, estimated token usage, current options |
| `/options` | List all current inference parameters |
| `/set temperature 0.3` | Change any inference parameter mid-session |
| `/system <text>` | Set a new system prompt (clears history) |
| `/model <name>` | Switch model mid-session (clears history, warms up new model) |
| `/quit` | Exit |

### Design Decisions

**Automatic warmup:** On startup, the REPL checks `is_model_loaded()` and calls `warmup()` if the model isn't resident. This means your first message always has fast TTFT — the loading cost is paid upfront, visibly, rather than silently on the first inference.

**`/set` for live parameter changes:** Rather than restarting the REPL to change temperature, you can adjust it in place. The new value takes effect on the next `.chat()` call because `session.options` is a mutable dict that's sent with every request.

**Model name in the prompt:** The response prefix shows the model's base name (`r1>`, `r1>`) rather than a generic `assistant>`. When you're experimenting with multiple models, this prevents confusion about which model produced which output.

---

## 9. Key Concepts and Gotchas

### The history growth problem

Every turn adds two messages to `session.history`. After N turns, the N+1th request sends 2N+1 messages. This has two effects:

1. **Prefill latency grows** — more tokens to process before generation begins
2. **Context budget shrinks** — at `num_ctx=4096`, a conversation with many long turns will eventually hit the limit

When the total token count exceeds `num_ctx`, Ollama silently drops the oldest messages from the left. **It does not warn you.** The model will lose the beginning of the conversation without any visible indication. Use `/stats` periodically to monitor your token budget.

### `/api/generate` and chat templates

If you use `/api/generate` with a raw prompt for a chat-tuned model (which DeepSeek R1 14B is), you're bypassing the model's chat template. The model was trained to expect specific special tokens (`<|im_start|>`, `<|im_end|>`, etc.) around user and assistant turns. Without them, multi-turn coherence degrades — the model may not properly "know" it's in a conversation.

For single-turn tasks (benchmarking, scripting, pipelines), this usually doesn't matter. For multi-turn conversation, always use `/api/chat`.

### The `eval_duration` vs wall-clock difference

Ollama's `eval_duration` field (nanoseconds) measures only the time spent generating tokens — it excludes model loading, KV cache setup, and the prefill phase. Wall-clock time (measured with `time.perf_counter()`) includes all of these.

For benchmarking, use `eval_duration` for pure generation speed (tok/s). Use wall-clock TTFT for the user-facing latency metric.

```python
# tok/s from Ollama's native measurement (more accurate)
eval_ns = final_chunk.get("eval_duration", 1)
tok_per_sec = output_tokens / (eval_ns / 1e9)

# Wall-clock TTFT (user experience metric)
ttft_ms = time_of_first_token - time_request_sent
```

### Import paths and the sys.path pattern

Because `benchmark/runner.py` lives in a subdirectory, Python's module resolution won't find `ollama_client` by default. The solution is to add the parent directory to `sys.path` at the top of the file:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

This is a pragmatic pattern for small projects. In a production codebase you'd install the package with `pip install -e .` using a `pyproject.toml` — but for a personal lab, the `sys.path` approach keeps things simple without requiring package installation.

---

## 10. Exercises

These exercises are designed to deepen understanding, not just test recall. Work through them in a notebook or as standalone scripts.

### Exercise 1 — Explore the raw NDJSON stream

Without using any helper functions, make a raw `requests.post` call to `/api/generate` with `stream=True` and print every line from the response as it arrives. Observe:

- How many tokens arrive per second?
- What does the final chunk (`done: true`) look like in full?
- What is `prompt_eval_duration` vs `eval_duration`?

```python
import requests, json

resp = requests.post(
    "http://localhost:11434/api/generate",
    json={"model": "deepseek-r1:14b", "prompt": "Count from 1 to 5.", "stream": True},
    stream=True,
)

for line in resp.iter_lines():
    if line:
        print(json.loads(line))
```

### Exercise 2 — Measure TTFT variance

Run the same prompt 10 times using `generate_with_stats` and collect the `ttft_ms` values. Compute mean and standard deviation. What is the coefficient of variation? What does a high CV tell you about system stability?

```python
from ollama_client import generate_with_stats
import statistics

results = [generate_with_stats("What is 2 + 2?", temperature=0) for _ in range(10)]
ttfts = [r["ttft_ms"] for r in results]

print(f"Mean TTFT : {statistics.mean(ttfts):.1f} ms")
print(f"Std TTFT  : {statistics.stdev(ttfts):.1f} ms")
print(f"CV        : {statistics.stdev(ttfts)/statistics.mean(ttfts):.2f}")
```

### Exercise 3 — Think token distribution

Run 5 prompts of increasing difficulty through `generate_with_stats` and plot think token count vs answer token count. Do harder problems produce longer think blocks? Is there a correlation between think tokens and answer quality?

### Exercise 4 — History budget monitor

Build a function that wraps `ChatSession.chat()` and prints a warning when `approx_tokens` exceeds 80% of `num_ctx`. Test it by having a very long conversation. Observe what happens to TTFT as history grows.

### Exercise 5 — Model switching benchmark

Use `warmup()` and `is_model_loaded()` to measure cold-start load time for both `deepseek-r1:14b` and `deepseek-r1:14b`. Then measure the first-inference TTFT and steady-state TTFT. How much does warm vs cold state affect the user experience?

---

## 11. Connection to the Rest of the Curriculum

Everything built in this module is reused directly in later modules:

**Module 5 — Inference parameters:** You'll use `stream_generate` with different temperature, top_p, and repeat_penalty values to observe how each parameter changes the output distribution in practice.

**Module 7 — Benchmark harness:** `runner.py` imports `is_model_loaded` and `warmup` from `ollama_client`. The harness uses `generate_with_stats` as its measurement core. The structured `RunResult` dataclass maps directly onto the Polars DataFrame schema.

**Phase 2 — RAG pipelines:** The `ChatSession` class becomes the conversational interface for retrieval-augmented generation. You'll inject retrieved document chunks into the system prompt or as user messages, and the existing history management handles the multi-turn context automatically.

**Phase 3 — Agents:** Multi-step agentic workflows require precise control over what the model sees (system prompt, context, history) and what comes back (structured parsing of tool calls). The `generate_with_stats` function's structured return format is the starting point for that parsing layer.

The design principle throughout: **build general tools, not single-use scripts**. The `ollama_client` package is more verbose than a collection of ad-hoc functions would be, but it pays dividends every time you reach for it in a new context.

---

## Quick Reference

```bash
# Start the REPL
cd ~/ai-lab && source .venv/bin/activate
python repl.py
python repl.py --model deepseek-r1:14b --temperature 0.6 --ctx 2048

# Inside the REPL
/reset                        # clear history
/stats                        # token budget and options
/set temperature 0.1          # change parameter live
/system You are a terse engineer who uses code examples.
/model deepseek-r1:14b        # switch model
/quit
```

```python
# Minimal usage examples

from ollama_client import stream_generate, generate_with_stats, ChatSession

# One-shot streaming
for tok in stream_generate("Explain GGUF format in one paragraph.", temperature=0):
    print(tok, end="", flush=True)

# Structured output with timing
result = generate_with_stats("How many r's in strawberry?")
print(result["answer"])
print(f"{result['tok_per_sec']} tok/s | TTFT {result['ttft_ms']}ms")

# Multi-turn conversation
session = ChatSession(
    system="You are a terse MLOps engineer.",
    options={"temperature": 0.4, "num_ctx": 4096}
)
session.chat("What is the KV cache?")
session.chat("How does it grow with context length?")
print(f"Turn {session.turn_count} | ~{session.approx_tokens} tokens used")
```

---

*Part of the Local LLM Inference Lab — Mac Mini M4 Pro · 24 GB unified memory*
*Modules: [1 Inference Stack] [2 Unified Memory] [3 Run R1 14B] [**4 Python Client**] [5 Parameters] [6 Local vs API] [7 Benchmark Harness]*
