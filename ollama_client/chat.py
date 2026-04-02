import json
from dataclasses import dataclass, field

import requests

from .config import OLLAMA_BASE, DEFAULT_MODEL, DEFAULT_OPTIONS


@dataclass
class ChatSession:
    model: str = DEFAULT_MODEL
    system: str = ""
    history: list = field(default_factory=list)
    options: dict = field(default_factory=lambda: dict(DEFAULT_OPTIONS))

    def chat(self, user_message: str) -> str:
        """Send a message, stream the reply, update history, return full reply."""
        self.history.append({"role": "user", "content": user_message})

        messages = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        messages.extend(self.history)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": self.options,
        }

        full_reply = ""
        try:
            with requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json=payload,
                stream=True,
                timeout=180,
            ) as resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    chunk = json.loads(raw_line)
                    tok = chunk.get("message", {}).get("content", "")
                    print(tok, end="", flush=True)
                    full_reply += tok
                    if chunk.get("done"):
                        break
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_BASE}. Is it running?")
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama chat timed out.")

        print()
        self.history.append({"role": "assistant", "content": full_reply})
        return full_reply

    def reset(self):
        self.history.clear()

    @property
    def turn_count(self) -> int:
        return len(self.history) // 2

    @property
    def approx_tokens(self) -> int:
        return sum(len(m["content"].split()) * 4 // 3 for m in self.history)
