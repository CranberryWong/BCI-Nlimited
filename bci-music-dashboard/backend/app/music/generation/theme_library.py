from __future__ import annotations

import random
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import mido
import yaml


@dataclass(frozen=True)
class ThemeNote:
    beat: float
    duration_beats: float
    pitch: int
    velocity: int


@dataclass(frozen=True)
class Theme:
    id: str
    title: str
    home_key: str
    mode: str
    beats_per_bar: int
    bars: int
    notes: tuple[ThemeNote, ...]
    anchors: frozenset[float]
    immutable_beats: frozenset[float]
    harmony: tuple[str, ...]
    phrases: tuple[dict, ...]
    emotion_variants: dict
    orchestration: dict
    license: dict
    path: Path

    def public_metadata(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "home_key": self.home_key,
            "mode": self.mode,
            "bars": self.bars,
            "license": self.license,
        }


class ThemeLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.themes: dict[str, Theme] = {}
        self.reload()

    def reload(self) -> None:
        self.themes = {}
        themes_dir = self.root / "themes"
        if not themes_dir.exists():
            return
        for arrangement in sorted(themes_dir.glob("*/arrangement.yaml")):
            theme = self._load(arrangement)
            self.themes[theme.id] = theme

    def list(self) -> list[dict]:
        return [theme.public_metadata() for theme in self.themes.values()]

    def select(self, theme_id: str = "random") -> Theme:
        if not self.themes:
            raise ValueError(f"no themes found in {self.root / 'themes'}")
        if theme_id == "random":
            return random.choice(list(self.themes.values()))
        try:
            return self.themes[theme_id]
        except KeyError as exc:
            raise ValueError(f"unknown theme: {theme_id}") from exc

    @staticmethod
    def _load(arrangement_path: Path) -> Theme:
        data = yaml.safe_load(arrangement_path.read_text(encoding="utf-8"))
        notes = ThemeLibrary._read_melody(arrangement_path.parent / "melody.mid")
        beats_per_bar = int(str(data.get("meter", "4/4")).split("/")[0])
        bars = max(1, ceil(max(note.beat + note.duration_beats for note in notes) / beats_per_bar))
        harmony = ["I"] * bars
        for item in data.get("harmony", []):
            start, end = item["bars"]
            for bar in range(start - 1, min(end, bars)):
                harmony[bar] = str(item["chord"])
        anchors = {
            float(beat)
            for phrase in data.get("phrases", [])
            for beat in phrase.get("anchors", [])
        }
        immutable = set(float(value) for value in data.get("immutable_beats", [])) | anchors
        return Theme(
            id=data["id"],
            title=data["title"],
            home_key=data.get("home_key", "C"),
            mode=data.get("mode", "major"),
            beats_per_bar=beats_per_bar,
            bars=bars,
            notes=tuple(notes),
            anchors=frozenset(anchors),
            immutable_beats=frozenset(immutable),
            harmony=tuple(harmony),
            phrases=tuple(data.get("phrases", [])),
            emotion_variants=data.get("emotion_variants", {}),
            orchestration=data.get("orchestration", {}),
            license=data.get("license", {}),
            path=arrangement_path.parent,
        )

    @staticmethod
    def _read_melody(path: Path) -> list[ThemeNote]:
        midi = mido.MidiFile(path)
        merged = mido.merge_tracks(midi.tracks)
        absolute = 0
        active: dict[tuple[int, int], tuple[int, int]] = {}
        notes: list[ThemeNote] = []
        for message in merged:
            absolute += message.time
            if message.type == "note_on" and message.velocity > 0 and not getattr(message, "is_meta", False):
                active[(message.channel, message.note)] = (absolute, message.velocity)
            elif message.type in {"note_off", "note_on"} and getattr(message, "note", None) is not None:
                started = active.pop((message.channel, message.note), None)
                if started:
                    start_tick, velocity = started
                    notes.append(ThemeNote(
                        beat=start_tick / midi.ticks_per_beat,
                        duration_beats=max(0.125, (absolute - start_tick) / midi.ticks_per_beat),
                        pitch=message.note,
                        velocity=velocity,
                    ))
        if not notes:
            raise ValueError(f"theme MIDI contains no notes: {path}")
        notes = sorted(notes, key=lambda note: note.beat)
        for previous, current in zip(notes, notes[1:]):
            if current.beat < previous.beat + previous.duration_beats - 0.01:
                raise ValueError(
                    f"theme MIDI must contain one non-overlapping melody: {path}"
                )
        return notes
