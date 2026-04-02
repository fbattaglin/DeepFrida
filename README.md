# AI Lab — Local LLM Inference

**Stack:** Mac Mini M4 Pro · 24 GB unified memory · Ollama 0.18.2 · Python 3.12

---

## Quickstart

```bash
cd ~/ai-lab
source .venv/bin/activate

# Interactive REPL
python repl.py
python repl.py --model deepseek-r1:14b --temperature 0.6 --ctx 2048
```

**REPL commands:**

| Command | Effect |
|---------|--------|
| `/reset` | Clear history, keep system prompt |
| `/stats` | Token budget and current options |
| `/set temperature 0.3` | Change any parameter live |
| `/system <text>` | Set system prompt (clears history) |
| `/model <name>` | Switch model mid-session |
| `/quit` | Exit |

---

## Overview

A structured Python client for the [Ollama](https://ollama.com) REST API — built as the foundation for benchmarking, RAG pipelines, and agentic workflows.

### `ollama_client` package

```python
from ollama_client import stream_generate, generate_with_stats, ChatSession

# Streaming generation
for tok in stream_generate("Explain GGUF format in one paragraph.", temperature=0):
    print(tok, end="", flush=True)

# Structured output with TTFT and tok/s
result = generate_with_stats("How many r's in strawberry?")
print(result["answer"])
print(f"{result['tok_per_sec']} tok/s | TTFT {result['ttft_ms']}ms")

# Multi-turn chat (manages history automatically)
session = ChatSession(system="You are a terse MLOps engineer.")
session.chat("What is the KV cache?")
session.chat("How does it grow with context length?")
```

### Key design points

- **`/api/generate`** — raw prompt, full control, used for benchmarking
- **`/api/chat`** — messages array with automatic chat-template formatting, used for conversation
- **Streaming (NDJSON)** — tokens arrive one per line; enables true TTFT measurement
- **`ChatSession`** — Ollama is stateless; the client maintains and replays full history on every turn
- **`warmup()`** — forces model into unified memory before benchmarking to separate cold-load cost from inference latency

### Project layout

```
ai-lab/
├── ollama_client/      # reusable client package
│   ├── config.py       # base URL, defaults
│   ├── generate.py     # stream_generate, generate_with_stats
│   ├── chat.py         # ChatSession
│   └── models.py       # list_models, is_model_loaded, warmup
├── repl.py             # interactive REPL
├── benchmark/          # Module 7 harness
└── notebooks/
```

---

*Modules: [1 Inference Stack] [2 Unified Memory] [3 Run R1 14B] [4 Python Client] [5 Parameters] [6 Local vs API] [7 Benchmark Harness]*
