from __future__ import annotations

import csv
import json
import time
import uuid
from pathlib import Path
from typing import Any

import mido
import yaml

from app.music.schemas import EmotionState, MusicEvent


class SessionRecorder:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_id: str | None = None
        self.active_dir: Path | None = None
        self.started_at: float | None = None
        self.emotions: list[EmotionState] = []
        self.events: list[MusicEvent] = []

    def start(self, config_snapshot: dict[str, Any]) -> str:
        if self.active_id:
            return self.active_id
        self.active_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.active_dir = self.root / self.active_id
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()
        self.emotions = []
        self.events = []
        (self.active_dir / "music_config_snapshot.yaml").write_text(
            yaml.safe_dump(config_snapshot, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return self.active_id

    def stop(self) -> str | None:
        if not self.active_id or not self.active_dir:
            return None
        session_id = self.active_id
        self._flush_jsonl()
        self._flush_csv()
        self._flush_midi()
        self.active_id = None
        self.active_dir = None
        self.started_at = None
        self.emotions = []
        self.events = []
        return session_id

    def record_emotion(self, emotion: EmotionState) -> None:
        if self.active_id:
            self.emotions.append(emotion)

    def record_event(self, event: MusicEvent) -> None:
        if self.active_id:
            self.events.append(event)

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for path in sorted(self.root.iterdir(), reverse=True):
            if path.is_dir():
                sessions.append({"id": path.name, "files": sorted(child.name for child in path.iterdir() if child.is_file())})
        return sessions

    def artifact(self, session_id: str, file_format: str) -> Path:
        filenames = {"mid": "music.mid", "jsonl": "timeline.jsonl", "csv": "emotion.csv"}
        if file_format not in filenames:
            raise KeyError(file_format)
        path = self.root / session_id / filenames[file_format]
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def _flush_jsonl(self) -> None:
        assert self.active_dir
        with (self.active_dir / "timeline.jsonl").open("w", encoding="utf-8") as handle:
            for emotion in self.emotions:
                handle.write(json.dumps({"kind": "emotion", **emotion.model_dump()}, ensure_ascii=False) + "\n")
            for event in self.events:
                handle.write(json.dumps({"kind": "music_event", **event.model_dump()}, ensure_ascii=False) + "\n")

    def _flush_csv(self) -> None:
        assert self.active_dir
        with (self.active_dir / "emotion.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(EmotionState.model_fields))
            writer.writeheader()
            for emotion in self.emotions:
                writer.writerow(emotion.model_dump())

    def _flush_midi(self) -> None:
        assert self.active_dir
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        midi.tracks.append(track)
        notes = [event for event in self.events if event.type in {"note_on", "note_off"} and event.pitch is not None]
        if not notes:
            midi.save(self.active_dir / "music.mid")
            return
        started = min(event.timestamp for event in notes)
        last_tick = 0
        for event in sorted(notes, key=lambda item: item.timestamp):
            tick = round((event.timestamp - started) * 960)
            track.append(
                mido.Message(
                    event.type,
                    note=event.pitch or 0,
                    velocity=event.velocity or 0,
                    channel=max(0, (event.channel or 1) - 1),
                    time=max(0, tick - last_tick),
                )
            )
            last_tick = tick
        midi.save(self.active_dir / "music.mid")
