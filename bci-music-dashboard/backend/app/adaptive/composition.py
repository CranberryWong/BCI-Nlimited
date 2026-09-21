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


def chord_intervals(symbol: str | None) -> tuple[int, int, int]:
    """Return triad intervals encoded by a supported Roman-numeral symbol."""
    if symbol and "°" in symbol:
        return (0, 3, 6)
    if symbol and symbol[:1].islower():
        return (0, 3, 7)
    return (0, 4, 7)


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
        self.transitions = dict(config.get("transitions", {}))
        self.minimum_phrases = max(1, int(config.get("minimum_phrases_per_section", 2)))
        self.maximum_phrases = max(
            self.minimum_phrases,
            int(config.get("maximum_phrases_per_section", 4)),
        )
        self.transition_confidence = float(config.get("transition_confidence", 0.6))
        self.state = self._state_for(0, phrase_index=0)

    def reset(self) -> FormState:
        self.state = self._state_for(0, phrase_index=0)
        return self.state.model_copy(deep=True)

    def advance_phrase(self, intent: MusicIntent) -> tuple[FormState, bool]:
        if self.state.completed:
            return self.state.model_copy(deep=True), False

        previous_section = self.state.section_index
        phrase_in_section = self.state.phrase_in_section + 1
        section_index = previous_section
        is_final = previous_section == max(0, len(self.sections) - 1)

        if is_final:
            next_state = self._state_for(section_index, phrase_index=self.state.phrase_index + 1)
            next_state.phrase_in_section = phrase_in_section
            next_state.emotion_changes_used = self.state.emotion_changes_used
            next_state.completed = phrase_in_section >= self.minimum_phrases
            self.state = next_state
            return self.state.model_copy(deep=True), False

        next_index = previous_section + 1
        current_id = str(self.sections[previous_section].get("id", ""))
        next_id = str(self.sections[next_index].get("id", ""))
        next_role = self.sections[next_index].get("role", "identity")
        allowed_targets = set(self.transitions.get(current_id, []))
        can_advance = phrase_in_section >= self.minimum_phrases and next_id in allowed_targets
        consumes_emotion_budget = next_role in {"contrast", "development", "climax"}
        has_emotion_budget = (
            not consumes_emotion_budget
            or self.state.emotion_changes_used < self.state.emotion_change_budget
        )
        emotion_driven = (
            intent.confidence >= self.transition_confidence
            and intent.transition_urgency >= self.transition_confidence
            and has_emotion_budget
        )
        forced_by_maximum = phrase_in_section >= self.maximum_phrases
        if can_advance and (emotion_driven or forced_by_maximum):
            section_index = next_index
            phrase_in_section = 0

        next_state = self._state_for(section_index, phrase_index=self.state.phrase_index + 1)
        next_state.phrase_in_section = phrase_in_section
        if section_index != previous_section and emotion_driven and consumes_emotion_budget:
            next_state.emotion_changes_used = self.state.emotion_changes_used + 1
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
        self.identity: MotifPlan | None = None
        self.counter = 0

    def plan(self, intent: MusicIntent, tonal: TonalPlan, form: FormState) -> MotifPlan:
        if intent.frozen_motif and self.current is not None:
            return self.current.model_copy(deep=True)
        self.counter += 1
        bars = int(self.config.get("bars", 2))
        beats_per_bar = int(self.config.get("beats_per_bar", 4))
        total_beats = bars * beats_per_bar
        subdivisions = sorted(
            {float(value) for value in self.config.get("allowed_subdivisions", [0.25, 0.5, 1.0])},
            reverse=True,
        )
        density = max(0.2, intent.density)
        duration = self._subdivision_for_density(density, subdivisions)
        contour = self._contour_for_valence(intent.valence)
        transform = self.config.get("transform_by_form", {}).get(form.role, "identity")
        root = NOTE_NAMES.get(tonal.root_note, 0)
        low, high = tonal.melody_range
        center = min(high, max(low, int(self.config.get("base_pitch", 60)) + root))
        anchor_config = self.config.get("anchors", {})
        anchors = {float(value) for value in anchor_config.get("beats", [0, 4, 7])}
        immutable_anchors = bool(anchor_config.get("immutable", True))
        notes: list[MotifNote] = []
        beat = 0.0
        index = 0
        while beat < total_beats:
            degree_index = self._degree_index(contour, index, len(tonal.pitch_classes))
            pitch = self._fit_to_range(center + tonal.pitch_classes[degree_index], low, high)
            articulation_accent = 0.12 if intent.articulation == "accented" else 0.05 if intent.articulation == "detached" else 0.0
            accent = min(1.0, (0.85 if beat % beats_per_bar == 0 else 0.55) + articulation_accent)
            velocity = round(42 + intent.energy * 62 + accent * 12)
            is_anchor = any(math.isclose(beat, anchor, abs_tol=1e-6) for anchor in anchors)
            notes.append(MotifNote(
                beat=beat,
                duration_beats=min(duration * (1.5 if is_anchor else 1.0), total_beats - beat),
                pitch=pitch,
                velocity=max(1, min(127, velocity)),
                anchor=is_anchor,
                mutable=not (is_anchor and immutable_anchors),
                accent=accent,
            ))
            beat += duration
            index += 1
        source = MotifPlan(
            id=f"adaptive-{self.counter:04d}",
            bars=bars,
            beats_per_bar=beats_per_bar,
            contour=contour,
            transform=transform,
            notes=notes,
        )
        self.current = self._apply_transform(source, transform, tonal, subdivisions)
        if transform == "identity":
            self.identity = self.current.model_copy(deep=True)
        return self.current.model_copy(deep=True)

    def _subdivision_for_density(self, density: float, subdivisions: list[float]) -> float:
        thresholds = self.config.get("density_thresholds", {})
        medium_above = float(thresholds.get("medium_above", 0.45))
        fast_above = float(thresholds.get("fast_above", 0.78))
        if density >= fast_above:
            return subdivisions[-1]
        if density >= medium_above:
            return subdivisions[len(subdivisions) // 2]
        return subdivisions[0]

    def _contour_for_valence(self, valence: float) -> str:
        thresholds = self.config.get("valence_thresholds", {})
        contours = self.config.get("contours", {})
        if valence <= float(thresholds.get("low_below", 0.38)):
            return str(contours.get("low_valence", "descending"))
        if valence >= float(thresholds.get("high_above", 0.62)):
            return str(contours.get("high_valence", "ascending"))
        return str(contours.get("neutral", "wave"))

    def _apply_transform(
        self,
        source: MotifPlan,
        transform: str,
        tonal: TonalPlan,
        subdivisions: list[float],
    ) -> MotifPlan:
        settings = self.config.get("transform_settings", {})
        notes = [note.model_copy(deep=True) for note in source.notes]
        total_beats = source.bars * source.beats_per_bar

        if transform == "recall" and self.identity is not None:
            notes = [
                note.model_copy(update={"pitch": self._snap_to_tonal(note.pitch, tonal)})
                for note in self.identity.notes
            ]
        elif transform == "simplify":
            stride = max(1, int(settings.get("simplify_stride", 2)))
            notes = [note for index, note in enumerate(notes) if note.anchor or index % stride == 0]
            for index, note in enumerate(notes):
                next_beat = notes[index + 1].beat if index + 1 < len(notes) else total_beats
                if note.mutable:
                    note.duration_beats = min(max(note.duration_beats, next_beat - note.beat), total_beats - note.beat)
        elif transform == "transpose":
            steps = int(settings.get("transpose_scale_steps", 1))
            notes = [
                note.model_copy(update={"pitch": self._transpose_scale_steps(note.pitch, steps, tonal)})
                if note.mutable else note
                for note in notes
            ]
        elif transform == "invert" and notes:
            center = next((note.pitch for note in notes if note.anchor), notes[0].pitch)
            notes = [
                note.model_copy(update={"pitch": self._snap_to_tonal(center - (note.pitch - center), tonal)})
                if note.mutable else note
                for note in notes
            ]
        elif transform == "compress":
            ratio = float(settings.get("compression_ratio", 0.5))
            minimum = subdivisions[-1]
            compressed: list[MotifNote] = []
            for note in notes:
                if not note.mutable:
                    compressed.append(note)
                    continue
                compressed.append(note.model_copy(update={
                    "duration_beats": max(minimum, note.duration_beats * ratio),
                }))
                next_beat = note.beat + max(minimum, note.duration_beats * ratio)
                if note.mutable and next_beat < min(total_beats, note.beat + note.duration_beats):
                    compressed.append(note.model_copy(update={
                        "beat": next_beat,
                        "duration_beats": max(minimum, note.duration_beats * ratio),
                        "pitch": self._transpose_scale_steps(note.pitch, 1, tonal),
                        "anchor": False,
                        "mutable": True,
                    }))
            notes = sorted(compressed, key=lambda note: note.beat)
        elif transform == "cadence" and notes:
            cadence_duration = float(settings.get("cadence_duration_beats", 2.0))
            last = notes[-1]
            tonic = self._nearest_pitch_class(last.pitch, NOTE_NAMES.get(tonal.root_note, 0), tonal.melody_range)
            notes[-1] = last.model_copy(update={
                "pitch": tonic,
                "duration_beats": min(cadence_duration, total_beats - last.beat),
            })

        return source.model_copy(update={"notes": notes})

    @staticmethod
    def _transpose_scale_steps(pitch: int, steps: int, tonal: TonalPlan) -> int:
        if steps == 0:
            return pitch
        low, high = tonal.melody_range
        root = NOTE_NAMES.get(tonal.root_note, 0)
        allowed = [value for value in range(low, high + 1) if (value - root) % 12 in tonal.pitch_classes]
        if not allowed:
            return max(low, min(high, pitch))
        index = min(range(len(allowed)), key=lambda item: abs(allowed[item] - pitch))
        return allowed[max(0, min(len(allowed) - 1, index + steps))]

    @staticmethod
    def _snap_to_tonal(pitch: int, tonal: TonalPlan) -> int:
        low, high = tonal.melody_range
        root = NOTE_NAMES.get(tonal.root_note, 0)
        allowed = [value for value in range(low, high + 1) if (value - root) % 12 in tonal.pitch_classes]
        return min(allowed, key=lambda value: abs(value - pitch)) if allowed else max(low, min(high, pitch))

    @staticmethod
    def _nearest_pitch_class(pitch: int, pitch_class: int, pitch_range: tuple[int, int]) -> int:
        low, high = pitch_range
        candidates = [value for value in range(low, high + 1) if value % 12 == pitch_class]
        return min(candidates, key=lambda value: abs(value - pitch)) if candidates else max(low, min(high, pitch))

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
        if (
            not self.config.get("enabled", True)
            or int(self.config.get("maximum_voices", 2)) < 2
            or form.role not in set(self.config.get("forms", []))
        ):
            return []
        delay = float(self.config.get("entry_delay_beats", 2))
        interval = int(self.config.get("interval_semitones", 7))
        invert = bool(self.config.get("allow_inversion", True)) and form.role == "development"
        center = motif.notes[0].pitch if motif.notes else 60
        result: list[MotifNote] = []
        for original in motif.notes:
            pitch = center - (original.pitch - center) if invert else original.pitch
            pitch += interval
            while pitch < 36:
                pitch += 12
            while pitch > 72:
                pitch -= 12
            result.append(original.model_copy(update={
                "beat": original.beat + delay,
                "pitch": max(0, min(127, pitch)),
                "velocity": max(1, original.velocity - 18),
                "anchor": False,
                "mutable": True,
            }))
        total = motif.bars * motif.beats_per_bar
        result = [note for note in result if note.beat < total]
        return self._remove_forbidden_parallels(result, motif, tonal)

    def _remove_forbidden_parallels(
        self,
        counterpoint: list[MotifNote],
        motif: MotifPlan,
        tonal: TonalPlan,
    ) -> list[MotifNote]:
        forbidden = set()
        if self.config.get("reject_parallel_fifths", True):
            forbidden.add(7)
        if self.config.get("reject_parallel_octaves", True):
            forbidden.add(0)
        if not forbidden:
            return counterpoint

        lead_by_beat = {round(note.beat, 6): note.pitch for note in motif.notes}
        root = NOTE_NAMES.get(tonal.root_note, 0)
        candidates = [
            pitch for pitch in range(36, 73)
            if (pitch - root) % 12 in set(tonal.pitch_classes)
        ]
        previous: tuple[int, int] | None = None
        corrected: list[MotifNote] = []
        for note in counterpoint:
            lead = lead_by_beat.get(round(note.beat, 6))
            pitch = note.pitch
            if lead is not None and previous is not None:
                previous_lead, previous_counter = previous
                same_direction = (
                    (lead - previous_lead) * (pitch - previous_counter) > 0
                )
                previous_interval = abs(previous_counter - previous_lead) % 12
                current_interval = abs(pitch - lead) % 12
                if same_direction and previous_interval == current_interval and current_interval in forbidden:
                    alternatives = sorted(candidates, key=lambda value: (abs(value - pitch), value))
                    pitch = next(
                        (
                            value for value in alternatives
                            if value != pitch and abs(value - lead) % 12 not in forbidden
                        ),
                        pitch,
                    )
            corrected_note = note.model_copy(update={"pitch": pitch})
            corrected.append(corrected_note)
            if lead is not None:
                previous = (lead, pitch)
        return corrected


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
        pad_voicings = []
        for symbol in progression:
            degree = ROMAN_DEGREES.get(str(symbol).replace("°", ""), 0)
            scale_degree = tonal.pitch_classes[degree % len(tonal.pitch_classes)]
            pc = (root_pc + scale_degree) % 12
            roots.append(pc)
            bass.append(36 + pc if pc <= 7 else 24 + pc)
            pad_voicings.append([48 + pc + interval for interval in chord_intervals(str(symbol))])
        rule = HarmonyPlan(
            chords=[str(value) for value in progression],
            roots=roots,
            bass_pitches=bass,
            pad_voicings=pad_voicings,
            counterpoint=self.counterpoint.generate(motif, tonal, form),
            provider="rule",
        )
        noto = self.config.get("notochord", {})
        if not noto.get("enabled", False):
            return rule
        roles = set(noto.get("roles", [])) & {"harmony", "bass", "inner_voice"}
        if not roles:
            return rule
        if self.provider_disabled_reason:
            return rule.model_copy(update={"fallback_reason": self.provider_disabled_reason})
        if self.candidate_provider is None or not getattr(self.candidate_provider, "available", False):
            return rule.model_copy(update={"fallback_reason": "Notochord provider unavailable"})
        try:
            pitches = await asyncio.wait_for(
                asyncio.to_thread(self.candidate_provider.propose, tonal, motif, form, rule, roles),
                timeout=max(0.01, float(noto.get("timeout_seconds", 0.20))),
            )
            if not isinstance(pitches, dict):
                raise ValueError("Notochord candidate response must be grouped by role")
            updates: dict[str, object] = {
                "provider": "notochord",
                "notochord_roles": sorted(roles),
            }
            if "bass" in roles:
                bass_pitches = pitches.get("bass", [])
                if len(bass_pitches) != len(rule.bass_pitches):
                    raise ValueError("Notochord bass candidate count mismatch")
                updates["bass_pitches"] = bass_pitches
            if "harmony" in roles:
                pad = pitches.get("harmony", [])
                if len(pad) != len(rule.pad_voicings) or any(len(voicing) != 3 for voicing in pad):
                    raise ValueError("Notochord harmony candidate count mismatch")
                updates["pad_voicings"] = pad
            if "inner_voice" in roles:
                inner = pitches.get("inner_voice", [])
                if len(inner) != len(rule.roots):
                    raise ValueError("Notochord inner-voice candidate count mismatch")
                updates["inner_pitches"] = inner
            return rule.model_copy(update=updates)
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

    def apply(
        self,
        event: CanonicalMusicEvent,
        tonal: TonalPlan,
        chord_root: int | None,
        beat_duration: float,
        chord_symbol: str | None = None,
    ) -> CanonicalMusicEvent:
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
        grid_size = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25}.get(
            str(self.config.get("guardrails", {}).get("soft_grid", "1/16")),
            0.25,
        )
        grid_beat = round(event.beat / grid_size) * grid_size
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
            chord_pitch_classes = {(chord_root + interval) % 12 for interval in chord_intervals(chord_symbol)}
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
