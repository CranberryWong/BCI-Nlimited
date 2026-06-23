from __future__ import annotations

import csv
import json
import time
import uuid
from pathlib import Path
from typing import Any

import mido
import yaml

from app.music.schemas import EmotionState, MusicEvent, MusicSegment


class SessionRecorder:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_id: str | None = None
        self.active_dir: Path | None = None
        self.started_at: float | None = None
        self.emotions: list[EmotionState] = []
        self.events: list[MusicEvent] = []
        self.segments: list[MusicSegment] = []
        self.generator_statuses: list[dict[str, Any]] = []
        self.model_metadata: dict[str, Any] = {}
        self.composition_metadata: dict[str, Any] = {}

    def start(self, config_snapshot: dict[str, Any]) -> str:
        if self.active_id:
            return self.active_id
        self.active_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.active_dir = self.root / self.active_id
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()
        self.emotions = []
        self.events = []
        self.segments = []
        self.generator_statuses = []
        self.composition_metadata = {}
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
        self.segments = []
        self.generator_statuses = []
        self.composition_metadata = {}
        return session_id

    def record_emotion(self, emotion: EmotionState) -> None:
        if self.active_id:
            self.emotions.append(emotion)

    def record_event(self, event: MusicEvent) -> None:
        if self.active_id:
            self.events.append(event)

    def record_segment(self, segment: MusicSegment) -> None:
        if self.active_id:
            self.segments.append(segment)
            self.composition_metadata = {
                "theme_id": segment.theme_id,
                "form_section": segment.form_section,
                "phrase_id": segment.phrase_id,
                "theme_similarity": segment.theme_similarity,
                "harmony": segment.harmony,
                "actual_max_voices": segment.actual_max_voices,
                "harmony_note_count": segment.harmony_note_count,
                "notochord_modified_count": segment.notochord_modified_count,
                "melody_notes": [
                    {
                        "beat": note.beat,
                        "pitch": note.pitch,
                        "voice_role": note.voice_role,
                        "generated_by": note.generated_by,
                    }
                    for note in segment.notes
                    if note.voice_role is not None
                ],
            }

    def record_generator_status(self, status: dict[str, Any]) -> None:
        if self.active_id:
            self.generator_statuses.append({"timestamp": time.time(), **status})

    def set_model_metadata(self, metadata: dict[str, Any]) -> None:
        self.model_metadata = metadata

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for path in sorted(self.root.iterdir(), reverse=True):
            if path.is_dir():
                sessions.append({"id": path.name, "files": sorted(child.name for child in path.iterdir() if child.is_file())})
        return sessions

    def artifact(self, session_id: str, file_format: str) -> Path:
        filenames = {
            "mid": "music.mid",
            "csv": "emotion.csv",
            "emotion-jsonl": "emotion_timeline.jsonl",
            "music-jsonl": "music_event_log.jsonl",
            "config": "music_config_snapshot.yaml",
            "segments": "music_segments.jsonl",
            "generator-status": "generator_status.json",
            "model-metadata": "model_metadata.json",
            "composition-metadata": "composition_metadata.json",
        }
        if file_format not in filenames:
            raise KeyError(file_format)
        path = self.root / session_id / filenames[file_format]
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def _flush_jsonl(self) -> None:
        assert self.active_dir
        with (self.active_dir / "emotion_timeline.jsonl").open("w", encoding="utf-8") as handle:
            for emotion in self.emotions:
                handle.write(json.dumps(emotion.model_dump(), ensure_ascii=False) + "\n")
        with (self.active_dir / "music_event_log.jsonl").open("w", encoding="utf-8") as handle:
            for event in self.events:
                handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        with (self.active_dir / "music_segments.jsonl").open("w", encoding="utf-8") as handle:
            for segment in self.segments:
                handle.write(json.dumps(segment.model_dump(), ensure_ascii=False) + "\n")
        (self.active_dir / "generator_status.json").write_text(
            json.dumps(self.generator_statuses, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.active_dir / "model_metadata.json").write_text(
            json.dumps(self.model_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.active_dir / "composition_metadata.json").write_text(
            json.dumps(self.composition_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
