import json
import time

import requests

from ollama_client.config import OLLAMA_BASE, DEFAULT_MODEL


def run_with_timing(prompt: str, model: str = DEFAULT_MODEL):
    url = f"{OLLAMA_BASE}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": True}

    think_tokens, answer_tokens = [], []
    in_think = False
    ttft = None
    t_start = time.perf_counter()

    with requests.post(url, json=payload, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            tok = chunk.get("response", "")

            if ttft is None and tok:
                ttft = time.perf_counter() - t_start

            if "<think>" in tok:
                in_think = True
            if "</think>" in tok:
                in_think = False

            if in_think or "<think>" in tok:
                think_tokens.append(tok)
            else:
                answer_tokens.append(tok)

            print(tok, end="", flush=True)

            if chunk.get("done"):
                elapsed = time.perf_counter() - t_start
                total_toks = chunk.get("eval_count", 0)
                prompt_toks = chunk.get("prompt_eval_count", 0)

                print(f"\n\n{'─'*50}")
                print(f"Time to first token : {ttft*1000:.0f} ms")
                print(f"Prompt tokens       : {prompt_toks}")
                print(f"Think tokens        : {len(think_tokens)}")
                print(f"Answer tokens       : {len(answer_tokens)}")
                print(f"Total gen time      : {elapsed:.1f} s")
                if elapsed > 0 and total_toks > 0:
                    print(f"Tokens/sec          : {total_toks/elapsed:.1f}")
                break


PROMPT = """A bat and a ball cost $1.10 in total.
The bat costs $1.00 more than the ball.
How much does the ball cost? Work through it carefully."""

run_with_timing(PROMPT)
