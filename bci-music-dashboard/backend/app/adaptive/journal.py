from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, TextIO

from .schemas import CanonicalMusicEvent, RuntimeLogEntry


class RuntimeJournal:
    def __init__(self, ring_size: int = 500) -> None:
        self.entries: deque[RuntimeLogEntry] = deque(maxlen=max(50, ring_size))
        self.events: deque[CanonicalMusicEvent] = deque(maxlen=max(100, ring_size * 2))
        self.sequence = 0
        self.session_id = ""
        self.path: Path | None = None
        self.handle: TextIO | None = None

    def start(self, session_id: str, session_dir: Path | None = None) -> None:
        self.session_id = session_id
        self.entries.clear()
        self.events.clear()
        self.sequence = 0
        self.path = session_dir / "runtime_event_log.jsonl" if session_dir else None
        self.handle = self.path.open("a", encoding="utf-8", buffering=1) if self.path else None

    def stop(self) -> None:
        if self.handle:
            self.handle.flush()
            self.handle.close()
        self.handle = None
        self.session_id = ""
        self.path = None

    def log(self, level: str, category: str, message: str, data: dict[str, Any] | None = None) -> RuntimeLogEntry:
        self.sequence += 1
        entry = RuntimeLogEntry(
            sequence=self.sequence,
            session_id=self.session_id,
            level=level,
            category=category,
            message=message,
            data=data or {},
        )
        self.entries.append(entry)
        self._persist("log", entry.model_dump())
        return entry

    def record_event(self, event: CanonicalMusicEvent) -> CanonicalMusicEvent:
        self.sequence += 1
        resolved = event.model_copy(update={"sequence": self.sequence, "session_id": event.session_id or self.session_id})
        self.events.append(resolved)
        self._persist("music_event", resolved.model_dump())
        return resolved

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        return [entry.model_dump() for entry in list(self.entries)[-max(1, min(limit, 500)):]]

    def _persist(self, kind: str, payload: dict[str, Any]) -> None:
        if not self.handle:
            return
        try:
            self.handle.write(json.dumps({"kind": kind, **payload}, ensure_ascii=False) + "\n")
        except OSError:
            self.handle = None
            return
