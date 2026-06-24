from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
import random
from typing import Any

import mido
import yaml

from app.music.schemas import EmotionLabel


@dataclass(frozen=True)
class MotifNote:
    beat: float
    duration_beats: float
    pitch: int
    velocity: int


@dataclass(frozen=True)
class Motif:
    id: str
    title: str
    emotion: EmotionLabel
    source_type: str
    home_key: str
    mode: str
    meter: str
    beats_per_bar: int
    bars: int
    tempo_hint: int
    pitch_range: tuple[int, int]
    notes: tuple[MotifNote, ...]
    anchors: frozenset[float]
    immutable_beats: frozenset[float]
    mutable_beats: frozenset[float]
    harmony: tuple[str, ...]
    phrases: tuple[dict[str, Any], ...]
    variation_allowed: dict[str, Any]
    portrait_behavior: dict[str, Any]
    orchestration: dict[str, Any]
    license: dict[str, Any]
    quality: dict[str, Any]
    performance: dict[str, Any]
    path: Path

    @property
    def approved(self) -> bool:
        return bool(self.quality.get("approved", False))

    @property
    def selectable(self) -> bool:
        return self.approved and 2 <= self.bars <= 8

    def public_metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "emotion": self.emotion,
            "home_key": self.home_key,
            "mode": self.mode,
            "bars": self.bars,
            "approved": self.approved,
            "selectable": self.selectable,
            "source_type": self.source_type,
            "performance": self.performance,
        }


class MotifValidationError(ValueError):
    pass


class MotifLibrary:
    REQUIRED_FIELDS = {
        "id",
        "title",
        "source_type",
        "emotion",
        "license",
        "meter",
        "bars",
        "home_key",
        "mode",
        "tempo_hint",
        "pitch_range",
        "phrases",
        "anchors",
        "immutable_beats",
        "mutable_beats",
        "harmony",
        "variation_allowed",
        "portrait_behavior",
        "orchestration",
        "quality",
    }

    def __init__(self, root: Path) -> None:
        self.root = root
        self.motifs: dict[str, Motif] = {}
        self.approved_by_emotion: dict[EmotionLabel, list[Motif]] = {
            "joy": [],
            "calm": [],
            "neutral": [],
            "tense": [],
            "sad": [],
        }
        self.errors: list[str] = []
        self.reload()

    def reload(self) -> None:
        self.motifs = {}
        self.approved_by_emotion = {key: [] for key in self.approved_by_emotion}
        self.errors = []
        motifs_dir = self.root / "motifs"
        if not motifs_dir.exists():
            return
        for yaml_path in sorted(motifs_dir.glob("*/*.yaml")):
            try:
                motif = self.load_motif(yaml_path)
            except Exception as exc:
                self.errors.append(f"{yaml_path}: {exc}")
                continue
            self.motifs[motif.id] = motif
            if motif.selectable:
                self.approved_by_emotion[motif.emotion].append(motif)

    def list(self, approved_only: bool = False) -> list[dict[str, Any]]:
        motifs = self.motifs.values()
        if approved_only:
            motifs = [motif for motif in motifs if motif.approved]
        return [motif.public_metadata() for motif in motifs]

    def select(self, emotion: EmotionLabel, avoid_id: str | None = None) -> Motif | None:
        candidates = list(self.approved_by_emotion.get(emotion, []))
        if avoid_id and len(candidates) > 1:
            candidates = [motif for motif in candidates if motif.id != avoid_id]
        performance_candidates = [
            motif for motif in candidates if motif.performance.get("polyphonic_melody")
        ]
        if performance_candidates:
            return random.choice(performance_candidates)
        if candidates:
            return random.choice(candidates)
        fallback = [
            motif
            for motifs in self.approved_by_emotion.values()
            for motif in motifs
            if motif.id != avoid_id
        ]
        performance_fallback = [
            motif for motif in fallback if motif.performance.get("polyphonic_melody")
        ]
        if performance_fallback:
            return random.choice(performance_fallback)
        return random.choice(fallback) if fallback else None

    @classmethod
    def load_motif(cls, yaml_path: Path) -> Motif:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        missing = sorted(cls.REQUIRED_FIELDS - set(data))
        if missing:
            raise MotifValidationError(f"missing required fields: {', '.join(missing)}")
        midi_path = yaml_path.with_suffix(".mid")
        if not midi_path.exists():
            raise MotifValidationError(f"missing MIDI pair: {midi_path.name}")
        performance = dict(data.get("performance", {}))
        if performance.get("polyphonic_melody"):
            notes, meter = read_motif_midi(midi_path, allow_overlaps=True)
        else:
            notes, meter = read_single_melody_midi(midi_path)
        if not notes:
            raise MotifValidationError("motif MIDI contains no notes")
        beats_per_bar = int(str(data.get("meter") or meter).split("/")[0])
        bars = int(data["bars"])
        if bars < ceil(max(note.beat + note.duration_beats for note in notes) / beats_per_bar):
            raise MotifValidationError("bars does not cover MIDI note range")
        anchors = frozenset(float(value) for value in data.get("anchors", []))
        immutable = frozenset(float(value) for value in data.get("immutable_beats", []))
        mutable = frozenset(float(value) for value in data.get("mutable_beats", []))
        note_beats = {round(note.beat, 3) for note in notes}
        missing_beats = sorted(
            value for value in anchors | immutable if round(value, 3) not in note_beats
        )
        if missing_beats:
            raise MotifValidationError(f"anchor/immutable beats missing in MIDI: {missing_beats}")
        harmony = expand_harmony(data.get("harmony", []), bars)
        if len(harmony) != bars or any(not chord for chord in harmony):
            raise MotifValidationError("harmony must cover every bar")
        emotion = data["emotion"]
        if emotion not in {"joy", "calm", "neutral", "tense", "sad"}:
            raise MotifValidationError(f"invalid emotion: {emotion}")
        pitch_range = tuple(data["pitch_range"])
        return Motif(
            id=str(data["id"]),
            title=str(data["title"]),
            emotion=emotion,
            source_type=str(data["source_type"]),
            home_key=str(data["home_key"]),
            mode=str(data["mode"]),
            meter=str(data["meter"]),
            beats_per_bar=beats_per_bar,
            bars=bars,
            tempo_hint=int(data["tempo_hint"]),
            pitch_range=(int(pitch_range[0]), int(pitch_range[1])),
            notes=tuple(notes),
            anchors=anchors,
            immutable_beats=immutable | anchors,
            mutable_beats=mutable,
            harmony=tuple(harmony),
            phrases=tuple(data.get("phrases", [])),
            variation_allowed=dict(data.get("variation_allowed", {})),
            portrait_behavior=dict(data.get("portrait_behavior", {})),
            orchestration=dict(data.get("orchestration", {})),
            license=dict(data.get("license", {})),
            quality=dict(data.get("quality", {})),
            performance=performance,
            path=yaml_path.parent,
        )


def read_single_melody_midi(path: Path) -> tuple[list[MotifNote], str]:
    return read_motif_midi(path, allow_overlaps=False)


def read_motif_midi(path: Path, allow_overlaps: bool = False) -> tuple[list[MotifNote], str]:
    midi = mido.MidiFile(path)
    merged = mido.merge_tracks(midi.tracks)
    meter = "4/4"
    absolute = 0
    active: dict[tuple[int, int], list[tuple[int, int]]] = {}
    notes: list[MotifNote] = []
    for message in merged:
        absolute += message.time
        if message.type == "time_signature":
            meter = f"{message.numerator}/{message.denominator}"
        if message.type == "note_on" and message.velocity > 0 and not getattr(message, "is_meta", False):
            key = (message.channel, message.note)
            if not allow_overlaps and key in active:
                raise MotifValidationError(f"overlapping same pitch note: {path}")
            active.setdefault(key, []).append((absolute, message.velocity))
        elif message.type in {"note_off", "note_on"} and getattr(message, "note", None) is not None:
            key = (message.channel, message.note)
            stack = active.get(key)
            started = stack.pop(0) if stack else None
            if stack == []:
                active.pop(key, None)
            if started:
                start_tick, velocity = started
                notes.append(MotifNote(
                    beat=round(start_tick / midi.ticks_per_beat, 3),
                    duration_beats=max(0.125, round((absolute - start_tick) / midi.ticks_per_beat, 3)),
                    pitch=message.note,
                    velocity=velocity,
                ))
    if active:
        raise MotifValidationError(f"unterminated notes in {path}")
    notes = sorted(notes, key=lambda note: (note.beat, note.pitch))
    if not allow_overlaps:
        for previous, current in zip(notes, notes[1:]):
            if current.beat < previous.beat + previous.duration_beats - 0.01:
                raise MotifValidationError(f"motif MIDI must contain one non-overlapping melody: {path}")
    return notes, meter


def expand_harmony(items: list[dict[str, Any]], bars: int) -> list[str]:
    harmony = [""] * bars
    for item in items:
        start, end = item["bars"]
        for bar in range(int(start) - 1, min(int(end), bars)):
            harmony[bar] = str(item["chord"])
    return harmony
