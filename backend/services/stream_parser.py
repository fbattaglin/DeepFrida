from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
TAG_PREFIXES = (THINK_OPEN, THINK_CLOSE)


@dataclass(frozen=True)
class StreamFragment:
    kind: Literal["think", "token"]
    content: str


class ThinkStreamParser:
    def __init__(self) -> None:
        self._in_think = False
        self._tag_buffer = ""
        self._answer_parts: list[str] = []
        self._think_parts: list[str] = []

    def feed_thinking(self, text: str) -> list[StreamFragment]:
        if not text:
            return []
        self._think_parts.append(text)
        return [StreamFragment(kind="think", content=text)]

    def _append(self, content: str) -> StreamFragment | None:
        if not content:
            return None
        if self._in_think:
            self._think_parts.append(content)
            return StreamFragment(kind="think", content=content)
        self._answer_parts.append(content)
        return StreamFragment(kind="token", content=content)

    def _drain_non_tag_prefix(self) -> list[StreamFragment]:
        emitted: list[StreamFragment] = []
        while self._tag_buffer and not any(tag.startswith(self._tag_buffer) for tag in TAG_PREFIXES):
            fragment = self._append(self._tag_buffer[0])
            self._tag_buffer = self._tag_buffer[1:]
            if fragment is not None:
                emitted.append(fragment)
        return emitted

    def feed_content(self, text: str) -> list[StreamFragment]:
        emitted: list[StreamFragment] = []
        position = 0

        while position < len(text):
            if self._tag_buffer:
                self._tag_buffer += text[position]
                position += 1

                if self._tag_buffer == THINK_OPEN:
                    self._in_think = True
                    self._tag_buffer = ""
                    continue

                if self._tag_buffer == THINK_CLOSE:
                    self._in_think = False
                    self._tag_buffer = ""
                    continue

                emitted.extend(self._drain_non_tag_prefix())
                continue

            tag_start = text.find("<", position)
            if tag_start == -1:
                fragment = self._append(text[position:])
                if fragment is not None:
                    emitted.append(fragment)
                break

            if tag_start > position:
                fragment = self._append(text[position:tag_start])
                if fragment is not None:
                    emitted.append(fragment)

            self._tag_buffer = "<"
            position = tag_start + 1
        return emitted

    def flush(self) -> list[StreamFragment]:
        if not self._tag_buffer:
            return []

        fragment = self._append(self._tag_buffer)
        self._tag_buffer = ""
        return [fragment] if fragment is not None else []

    @property
    def answer(self) -> str:
        return "".join(self._answer_parts).strip()

    @property
    def think(self) -> str:
        return "".join(self._think_parts).strip()
