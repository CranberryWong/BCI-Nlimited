"""Library for the bar-aligned machine-xylophone portrait assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido
import yaml

from app.music.schemas import EmotionLabel


@dataclass(frozen=True)
class PortraitNote:
    beat: float
    duration_beats: float
    pitch: int
    velocity: int
    source_track: str


@dataclass(frozen=True)
class PortraitAsset:
    id: str
    title: str
    emotion: EmotionLabel
    role: str
    meter: str
    bars: int
    beats_per_bar: int
    bpm: int
    home_key: str
    mode: str
    cadence: str
    loopable: bool
    same_key_minimum_interval_seconds: float
    notes: tuple[PortraitNote, ...]
    path: Path

    def public_metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "emotion": self.emotion,
            "role": self.role,
            "meter": self.meter,
            "bars": self.bars,
            "bpm": self.bpm,
            "loopable": self.loopable,
            "same_key_minimum_interval_seconds": self.same_key_minimum_interval_seconds,
        }


class PortraitLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.assets: dict[str, PortraitAsset] = {}
        self.errors: list[str] = []
        self.reload()

    def reload(self) -> None:
        self.assets = {}
        self.errors = []
        for yaml_path in sorted((self.root / "generated").glob("*/*.yaml")):
            try:
                asset = self._load(yaml_path)
            except Exception as exc:
                self.errors.append(f"{yaml_path}: {exc}")
                continue
            self.assets[asset.id] = asset

    def list(self) -> list[dict[str, Any]]:
        return [
            asset.public_metadata()
            for asset in self.assets.values()
            if "_machine" in asset.id
        ]

    def select(self, emotion: EmotionLabel, role: str) -> PortraitAsset | None:
        candidates = [asset for asset in self.assets.values() if asset.emotion == emotion and asset.role == role]
        if not candidates and role == "loop":
            candidates = [asset for asset in self.assets.values() if asset.emotion == emotion and asset.role == "sketch"]
        if not candidates:
            candidates = [asset for asset in self.assets.values() if asset.emotion == emotion and asset.role == "loop"]
        return min(candidates, key=lambda asset: ("_machine" not in asset.id, asset.id)) if candidates else None

    @staticmethod
    def _load(yaml_path: Path) -> PortraitAsset:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        meter = str(data["meter"])
        numerator, denominator = (int(item) for item in meter.split("/", 1))
        beats_per_bar = round(numerator * 4 / denominator)
        midi_path = yaml_path.with_suffix(".mid")
        if not midi_path.exists():
            raise ValueError(f"missing MIDI: {midi_path.name}")
        notes = PortraitLibrary._read_midi(midi_path)
        if not notes:
            raise ValueError("MIDI contains no notes")
        # The confirmed initial sketches are the stable loop layer of each portrait.
        role = str(data.get("role") or "loop")
        return PortraitAsset(
            id=str(data["id"]), title=str(data["title"]), emotion=str(data["emotion"]), role=role,
            meter=meter, bars=int(data["bars"]), beats_per_bar=beats_per_bar,
            bpm=int(data.get("tempo_bpm", 72)), home_key=str(data.get("home_key", "C")),
            mode=str(data.get("mode", "major")), cadence=str(data.get("cadence", "open")),
            loopable=bool(data.get("loopable", False)),
            same_key_minimum_interval_seconds=float(data.get("same_key_minimum_interval_seconds", 1.0)),
            notes=tuple(notes), path=yaml_path.parent,
        )

    @staticmethod
    def _read_midi(path: Path) -> list[PortraitNote]:
        midi = mido.MidiFile(path)
        notes: list[PortraitNote] = []
        for track in midi.tracks:
            track_name = ""
            absolute = 0
            active: dict[tuple[int, int], tuple[int, int]] = {}
            for message in track:
                absolute += message.time
                if message.type == "track_name":
                    track_name = message.name
                elif message.type == "note_on" and message.velocity > 0:
                    active[(message.channel, message.note)] = (absolute, message.velocity)
                elif message.type in {"note_off", "note_on"} and getattr(message, "note", None) is not None:
                    started = active.pop((message.channel, message.note), None)
                    if started:
                        start, velocity = started
                        notes.append(PortraitNote(
                            beat=round(start / midi.ticks_per_beat, 3),
                            duration_beats=max(.125, round((absolute - start) / midi.ticks_per_beat, 3)),
                            pitch=message.note, velocity=velocity, source_track=track_name,
                        ))
            if active:
                raise ValueError(f"unterminated notes in track {track_name}")
        return sorted(notes, key=lambda note: (note.beat, note.source_track, note.pitch))
