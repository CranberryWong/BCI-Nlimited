from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field

from .schemas import (
    CanonicalMusicEvent,
    FormState,
    HarmonyPlan,
    MotifNote,
    MotifPlan,
    MusicIntent,
    OrchestrationPlan,
    TonalPlan,
)


NOTE_NAMES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
ROMAN_DEGREES = {"I": 0, "ii": 1, "iii": 2, "IV": 3, "V": 4, "vi": 5, "vii": 6}


class TonalPlanner:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.current: TonalPlan | None = None

    def plan(self, intent: MusicIntent, section_changed: bool = False) -> TonalPlan:
        if self.current is not None and not section_changed:
            return self.current
        scale_name = self.config.get("neutral_scale", "shang")
        if intent.valence >= 0.62:
            scale_name = self.config.get("positive_scale", "gong")
        elif intent.valence <= 0.38:
            scale_name = self.config.get("negative_scale", "yu")
        scales = self.config.get("scales", {})
        self.current = TonalPlan(
            root_note=self.config.get("default_root", "C"),
            scale=scale_name,
            pitch_classes=list(scales.get(scale_name, [0, 2, 4, 7, 9])),
            melody_range=tuple(self.config.get("melody_range", [48, 84])),
            strong_beat_degrees=list(self.config.get("strong_beat_degrees", [0, 2, 4])),
        )
        return self.current


class FormEngine:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.sections = list(config.get("sections", []))
        self.minimum_phrases = max(1, int(config.get("minimum_phrases_per_section", 2)))
        self.state = self._state_for(0, phrase_index=0)

    def reset(self) -> FormState:
        self.state = self._state_for(0, phrase_index=0)
        return self.state.model_copy(deep=True)

    def advance_phrase(self, intent: MusicIntent) -> tuple[FormState, bool]:
        previous_section = self.state.section_index
        phrase_in_section = self.state.phrase_in_section + 1
        section_index = previous_section
        can_advance = phrase_in_section >= self.minimum_phrases
        # High urgency may advance at the minimum boundary; otherwise keep one
        # additional phrase to preserve musical stability.
        if can_advance and (intent.transition_urgency >= 0.45 or phrase_in_section > self.minimum_phrases):
            section_index = min(previous_section + 1, max(0, len(self.sections) - 1))
            phrase_in_section = 0 if section_index != previous_section else phrase_in_section
        next_state = self._state_for(section_index, phrase_index=self.state.phrase_index + 1)
        next_state.phrase_in_section = phrase_in_section
        if section_index != previous_section and next_state.role in {"contrast", "development", "climax"}:
            next_state.emotion_changes_used = min(self.state.emotion_change_budget, self.state.emotion_changes_used + 1)
        else:
            next_state.emotion_changes_used = self.state.emotion_changes_used
        self.state = next_state
        return self.state.model_copy(deep=True), section_index != previous_section

    def _state_for(self, index: int, phrase_index: int) -> FormState:
        if not self.sections:
            section = {"id": "A", "role": "identity"}
            index = 0
        else:
            index = min(index, len(self.sections) - 1)
            section = self.sections[index]
        return FormState(
            section_id=str(section.get("id", f"section-{index}")),
            role=section.get("role", "identity"),
            section_index=index,
            phrase_index=phrase_index,
            phrase_in_section=0,
            section_count=max(1, len(self.sections)),
            emotion_change_budget=int(self.config.get("emotion_change_budget", 3)),
            is_final=index == max(0, len(self.sections) - 1),
        )


class MotifEngine:
    def __init__(self, config: dict, seed: int = 0) -> None:
        self.config = config
        self.rng = random.Random(seed)
        self.current: MotifPlan | None = None
        self.counter = 0

    def plan(self, intent: MusicIntent, tonal: TonalPlan, form: FormState) -> MotifPlan:
        if intent.frozen_motif and self.current is not None:
            return self.current.model_copy(deep=True)
        self.counter += 1
        bars = int(self.config.get("bars", 2))
        beats_per_bar = int(self.config.get("beats_per_bar", 4))
        total_beats = bars * beats_per_bar
        subdivisions = list(self.config.get("allowed_subdivisions", [0.5, 1.0]))
        density = max(0.2, intent.density)
        duration = 1.0 if density < 0.45 else 0.5 if density < 0.78 else min(subdivisions)
        contour = "descending" if intent.valence < 0.38 else "ascending" if intent.valence > 0.62 else "wave"
        transform = self.config.get("transform_by_form", {}).get(form.role, "identity")
        root = NOTE_NAMES.get(tonal.root_note, 0)
        low, high = tonal.melody_range
        center = min(high, max(low, int(self.config.get("base_pitch", 60)) + root))
        anchors = {float(value) for value in self.config.get("anchors", {}).get("beats", [0, 4, 7])}
        notes: list[MotifNote] = []
        beat = 0.0
        index = 0
        while beat < total_beats:
            degree_index = self._degree_index(contour, index, len(tonal.pitch_classes))
            pitch = self._fit_to_range(center + tonal.pitch_classes[degree_index], low, high)
            articulation_accent = 0.12 if intent.articulation == "accented" else 0.05 if intent.articulation == "detached" else 0.0
            accent = min(1.0, (0.85 if beat % beats_per_bar == 0 else 0.55) + articulation_accent)
            velocity = round(42 + intent.energy * 62 + accent * 12)
            notes.append(MotifNote(
                beat=beat,
                duration_beats=min(duration * (1.5 if beat in anchors else 1.0), total_beats - beat),
                pitch=pitch,
                velocity=max(1, min(127, velocity)),
                anchor=beat in anchors,
                mutable=beat not in anchors,
                accent=accent,
            ))
            beat += duration
            index += 1
        self.current = MotifPlan(
            id=f"adaptive-{self.counter:04d}",
            bars=bars,
            beats_per_bar=beats_per_bar,
            contour=contour,
            transform=transform,
            notes=notes,
        )
        return self.current.model_copy(deep=True)

    @staticmethod
    def _degree_index(contour: str, index: int, size: int) -> int:
        if contour == "ascending":
            return index % size
        if contour == "descending":
            return (size - 1 - index) % size
        wave = list(range(size)) + list(range(size - 2, 0, -1))
        return wave[index % len(wave)] if wave else 0

    @staticmethod
    def _fit_to_range(pitch: int, low: int, high: int) -> int:
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        return max(low, min(high, pitch))


class CounterpointStrategy:
    def __init__(self, config: dict) -> None:
        self.config = config

    def generate(self, motif: MotifPlan, tonal: TonalPlan, form: FormState) -> list[MotifNote]:
        if not self.config.get("enabled", True) or form.role not in set(self.config.get("forms", [])):
            return []
        delay = float(self.config.get("entry_delay_beats", 2))
        interval = int(self.config.get("interval_semitones", 7))
        invert = bool(self.config.get("allow_inversion", True)) and form.role == "development"
        center = motif.notes[0].pitch if motif.notes else 60
        result: list[MotifNote] = []
        for original in motif.notes:
            pitch = center - (original.pitch - center) if invert else original.pitch
            pitch -= interval
            while pitch < 36:
                pitch += 12
            while pitch > 72:
                pitch -= 12
            if pitch == original.pitch or abs(pitch - original.pitch) % 12 in {0, 7}:
                pitch -= 2
            result.append(original.model_copy(update={
                "beat": original.beat + delay,
                "pitch": max(0, min(127, pitch)),
                "velocity": max(1, original.velocity - 18),
                "anchor": False,
                "mutable": True,
            }))
        total = motif.bars * motif.beats_per_bar
        return [note for note in result if note.beat < total]


class HarmonyEngine:
    def __init__(self, config: dict, candidate_provider=None) -> None:
        self.config = config
        self.counterpoint = CounterpointStrategy(config.get("counterpoint", {}))
        self.candidate_provider = candidate_provider
        self.provider_disabled_reason = ""

    async def plan(self, tonal: TonalPlan, motif: MotifPlan, form: FormState) -> HarmonyPlan:
        progression = self.config.get("progressions", {}).get(form.role) or self.config.get("progressions", {}).get("identity", ["I", "IV", "V", "I"])
        root_pc = NOTE_NAMES.get(tonal.root_note, 0)
        roots = []
        bass = []
        for symbol in progression:
            degree = ROMAN_DEGREES.get(str(symbol).replace("°", ""), 0)
            scale_degree = tonal.pitch_classes[degree % len(tonal.pitch_classes)]
            pc = (root_pc + scale_degree) % 12
            roots.append(pc)
            bass.append(36 + pc if pc <= 7 else 24 + pc)
        rule = HarmonyPlan(
            chords=[str(value) for value in progression],
            roots=roots,
            bass_pitches=bass,
            counterpoint=self.counterpoint.generate(motif, tonal, form),
            provider="rule",
        )
        noto = self.config.get("notochord", {})
        if not noto.get("enabled", False):
            return rule
        if self.provider_disabled_reason:
            return rule.model_copy(update={"fallback_reason": self.provider_disabled_reason})
        if self.candidate_provider is None or not getattr(self.candidate_provider, "available", False):
            return rule.model_copy(update={"fallback_reason": "Notochord provider unavailable"})
        try:
            pitches = await asyncio.wait_for(
                asyncio.to_thread(self.candidate_provider.propose, tonal, motif, form, rule),
                timeout=max(0.01, float(noto.get("timeout_seconds", 0.20))),
            )
            if len(pitches) != len(rule.bass_pitches):
                raise ValueError("Notochord candidate count mismatch")
            return rule.model_copy(update={"bass_pitches": pitches, "provider": "notochord"})
        except Exception as exc:
            self.provider_disabled_reason = f"Notochord disabled for this session after failure: {exc}"
            return rule.model_copy(update={"fallback_reason": self.provider_disabled_reason})


class OrchestrationEngine:
    def __init__(self, config: dict) -> None:
        self.config = config

    def plan(self, intent: MusicIntent, form: FormState) -> OrchestrationPlan:
        densities: dict[str, float] = {}
        velocities: dict[str, int] = {}
        enabled: list[str] = []
        for role, raw in self.config.get("roles", {}).items():
            if not raw.get("enabled", True):
                continue
            enabled.append(role)
            base_density = float(raw.get("base_density", 0.3))
            if role == "snare":
                density = base_density * (0.45 + intent.energy * 0.75 + intent.transition_urgency * 0.30)
            elif role == "cymbal":
                density = base_density * (0.25 + intent.transition_urgency * 1.25)
            elif role == "kick":
                density = base_density * (0.55 + intent.pulse * 0.65)
            elif role in {"pad", "fx"}:
                density = base_density * (1.25 - intent.energy * 0.45)
            else:
                density = base_density * (0.55 + intent.density * 0.75)
            if form.role in {"intro", "coda"} and role in {"snare", "cymbal", "kick"}:
                density *= 0.45
            densities[role] = max(0.0, min(1.0, density))
            velocities[role] = max(1, min(127, round(float(raw.get("base_velocity", 70)) * (0.65 + intent.energy * 0.55))))
        stems = self.config.get("stems", {})
        return OrchestrationPlan(
            role_density=densities,
            role_velocity=velocities,
            enabled_roles=enabled,
            stem_gain=float(stems.get("default_gain", 0.15)) if stems.get("enabled", True) else 0.0,
            magenta_audio_gain=0.20,
        )


class PromptCompiler:
    def __init__(self, config: dict) -> None:
        self.config = config

    def compile(self, intent: MusicIntent, form: FormState) -> str:
        mood = "bright" if intent.valence > 0.65 else "reflective" if intent.valence < 0.35 else "balanced"
        energy = "energetic" if intent.energy > 0.68 else "spacious" if intent.energy < 0.35 else "flowing"
        return str(self.config.get("prompt_template", "{mood} {energy} solo marimba improvisation")).format(
            mood=mood,
            energy=energy,
            articulation=intent.articulation,
            form=form.role,
        )


@dataclass
class MelodyGuard:
    config: dict
    last_pitch: int | None = field(default=None, init=False)
    active_pitches: dict[int, int] = field(default_factory=dict, init=False)

    def apply(self, event: CanonicalMusicEvent, tonal: TonalPlan, chord_root: int | None, beat_duration: float) -> CanonicalMusicEvent:
        if event.pitch is None or event.type not in {"note_on", "note_off"}:
            return event
        low, high = self.config.get("transcription", {}).get("pitch_range", [48, 96])
        original_pitch = int(event.pitch)
        if event.type == "note_off" and original_pitch in self.active_pitches:
            pitch = self.active_pitches.pop(original_pitch)
            return event.model_copy(update={
                "pitch": pitch,
                "duration_ms": 0,
                "metadata": {**event.metadata, "guarded": pitch != original_pitch, "original_pitch": original_pitch},
            })
        pitch = original_pitch
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        root = NOTE_NAMES.get(tonal.root_note, 0)
        allowed = {(root + pc) % 12 for pc in tonal.pitch_classes}
        if self.config.get("guardrails", {}).get("scale_snap", True) and pitch % 12 not in allowed:
            pitch = min(range(max(low, pitch - 2), min(high, pitch + 2) + 1), key=lambda value: (value % 12 not in allowed, abs(value - pitch)))
        if (
            event.type == "note_on"
            and self.config.get("guardrails", {}).get("octave_suppression", True)
            and self.last_pitch is not None
            and abs(pitch - self.last_pitch) > 12
        ):
            octave_choices = [candidate for candidate in range(low, high + 1) if candidate % 12 == pitch % 12]
            pitch = min(octave_choices, key=lambda candidate: abs(candidate - self.last_pitch))
        tolerance_ms = float(self.config.get("guardrails", {}).get("snap_tolerance_ms", 45))
        grid_beat = round(event.beat * 4) / 4
        distance_ms = abs(event.beat - grid_beat) * beat_duration * 1000
        if distance_ms <= tolerance_ms:
            event = event.model_copy(update={"beat": grid_beat})
        strong_corrected = False
        if (
            event.type == "note_on"
            and chord_root is not None
            and self.config.get("guardrails", {}).get("strong_beat_chord_snap", True)
            and abs(event.beat - round(event.beat)) * beat_duration * 1000 <= tolerance_ms
        ):
            chord_pitch_classes = {chord_root % 12, (chord_root + 4) % 12, (chord_root + 7) % 12}
            if pitch % 12 not in chord_pitch_classes:
                choices = [candidate for candidate in range(low, high + 1) if candidate % 12 in chord_pitch_classes]
                pitch = min(choices, key=lambda candidate: abs(candidate - pitch))
                strong_corrected = True
        minimum_ms = int(self.config.get("transcription", {}).get("minimum_note_ms", 80))
        duration = max(minimum_ms, event.duration_ms or minimum_ms) if event.type == "note_on" else 0
        metadata = {
            **event.metadata,
            "guarded": pitch != event.pitch,
            "original_pitch": event.pitch,
            "strong_beat_corrected": strong_corrected,
        }
        if event.type == "note_on":
            self.last_pitch = pitch
            self.active_pitches[original_pitch] = pitch
        return event.model_copy(update={"pitch": pitch, "duration_ms": duration, "metadata": metadata})


def motif_to_pianoroll(motif: MotifPlan, beat: float) -> list[int]:
    """Return the MRT2 128-pitch conditioning state for one 40ms frame."""
    state = [0] * 128
    for note in motif.notes:
        local = beat % (motif.bars * motif.beats_per_bar)
        if note.beat <= local < note.beat + note.duration_beats:
            state[note.pitch] = 2 if abs(local - note.beat) < 0.02 else 1
    return state
