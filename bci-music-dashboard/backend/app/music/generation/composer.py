from __future__ import annotations

import random
import time
import uuid

from app.music.scales import root_pc, scale_notes
from app.music.schemas import EmotionLabel, EmotionState, MusicSegment, SegmentNote, TrackConfig


EMOTION_SCALES: dict[EmotionLabel, tuple[str, ...]] = {
    "joy": ("gong", "zhi"),
    "calm": ("gong",),
    "neutral": ("gong", "shang"),
    "tense": ("jue",),
    "sad": ("yu",),
}


class RuleComposer:
    def compose(
        self,
        emotion: EmotionState,
        previous_emotion: EmotionLabel,
        bpm: int,
        tracks: list[TrackConfig],
        previous: MusicSegment | None = None,
        bars: int = 4,
        beats_per_bar: int = 4,
    ) -> MusicSegment:
        started = time.perf_counter()
        melody_track = self._track(tracks, "melody")
        scale = random.choice(EMOTION_SCALES[emotion.label])
        root_note = melody_track.root_note if melody_track.root_note != "auto" else "C"
        notes = scale_notes(root_pc(root_note), scale, *melody_track.pitch_range)
        motif = self._motif(notes, emotion, previous)
        melody = self._melody_notes(
            motif,
            notes,
            emotion,
            melody_track,
            bars,
            beats_per_bar,
            previous,
            root_note,
        )
        segment_notes = melody
        accompaniment = self._optional_track(tracks, "chord")
        if accompaniment:
            segment_notes += self._accompaniment(accompaniment, root_note, scale, bars, beats_per_bar, emotion)
        drum = self._optional_track(tracks, "drum")
        if drum:
            segment_notes += self._drums(drum, bars, beats_per_bar, emotion)
        cymbal = self._optional_track(tracks, "cymbal")
        if cymbal:
            segment_notes += self._cymbals(cymbal, emotion, previous_emotion, bars, beats_per_bar)
        return MusicSegment(
            id=uuid.uuid4().hex[:12],
            emotion=emotion.label,
            previous_emotion=previous_emotion,
            bpm=bpm,
            bars=bars,
            beats_per_bar=beats_per_bar,
            root_note=root_note,
            scale=scale,
            source="rule",
            generation_ms=(time.perf_counter() - started) * 1000,
            notes=sorted(segment_notes, key=lambda item: (item.beat, item.track_id, item.pitch)),
        )

    def _motif(
        self,
        scale: list[int],
        emotion: EmotionState,
        previous: MusicSegment | None,
    ) -> list[int]:
        if previous:
            previous_melody = [note.pitch for note in previous.notes if "melody" in note.track_id]
            if len(previous_melody) >= 4:
                shift = random.choice((-2, 0, 2))
                return [min(scale, key=lambda pitch: abs(pitch - (value + shift))) for value in previous_melody[:4]]
        center = round((len(scale) - 1) * (0.35 + emotion.valence_norm * 0.3))
        index = max(1, min(len(scale) - 3, center))
        directions = {
            "joy": (0, 1, 2, 1),
            "calm": (0, 1, 0, -1),
            "neutral": (0, 1, -1, 0),
            "tense": (0, 2, 1, 3),
            "sad": (0, -1, -2, -1),
        }[emotion.label]
        return [scale[max(0, min(len(scale) - 1, index + offset))] for offset in directions]

    def _melody_notes(
        self,
        motif: list[int],
        scale: list[int],
        emotion: EmotionState,
        track: TrackConfig,
        bars: int,
        beats_per_bar: int,
        previous: MusicSegment | None,
        root_note: str,
    ) -> list[SegmentNote]:
        step = 0.5 if emotion.arousal_norm >= 0.62 else 1.0
        if emotion.label in {"calm", "sad"}:
            step = 1.0
        notes: list[SegmentNote] = []
        previous_last = None
        if previous:
            prior = [note for note in previous.notes if note.track_id == track.id]
            previous_last = prior[-1].pitch if prior else None
        total_beats = bars * beats_per_bar
        beat = 0.0
        index = 0
        while beat < total_beats:
            bar = int(beat // beats_per_bar)
            phrase_index = int((beat % beats_per_bar) / step)
            base = motif[phrase_index % len(motif)]
            if bar == 1 and phrase_index == len(motif) - 1:
                base = min(scale, key=lambda pitch: abs(pitch - (base + random.choice((-2, 2)))))
            elif bar == 2:
                base = min(scale, key=lambda pitch: abs(pitch - (base + 2)))
            elif bar == bars - 1 and beat >= total_beats - 2:
                tonic_candidates = [
                    pitch for pitch in scale if pitch % 12 == root_pc(root_note)
                ]
                base = min(tonic_candidates or scale, key=lambda pitch: abs(pitch - motif[0]))
            if index == 0 and previous_last is not None and abs(base - previous_last) > 7:
                base = min(scale, key=lambda pitch: abs(pitch - previous_last))
            duration = min(step * (1.5 if emotion.label in {"calm", "sad"} else 0.9), total_beats - beat)
            velocity = round(track.velocity_range[0] + (track.velocity_range[1] - track.velocity_range[0]) * (0.3 + emotion.arousal_norm * 0.45))
            notes.append(
                SegmentNote(
                    beat=beat,
                    duration_beats=max(0.25, duration),
                    pitch=base,
                    velocity=max(1, min(127, velocity)),
                    track_id=track.id,
                    channel=track.midi_channel,
                )
            )
            beat += step
            index += 1
        return notes

    def _accompaniment(
        self,
        track: TrackConfig,
        root_note: str,
        scale: str,
        bars: int,
        beats_per_bar: int,
        emotion: EmotionState,
    ) -> list[SegmentNote]:
        available = scale_notes(root_pc(root_note), scale, *track.pitch_range)
        root = available[0] if available else track.pitch_range[0]
        fifth = min(available or [root], key=lambda pitch: abs(pitch - (root + 7)))
        velocity = round(track.velocity_range[0] + (track.velocity_range[1] - track.velocity_range[0]) * 0.35)
        result: list[SegmentNote] = []
        for bar in range(bars):
            beat = bar * beats_per_bar
            for pitch in (root, fifth):
                result.append(SegmentNote(
                    beat=beat,
                    duration_beats=beats_per_bar * 0.9,
                    pitch=pitch,
                    velocity=velocity,
                    track_id=track.id,
                    channel=track.midi_channel,
                ))
        return result

    def _drums(self, track: TrackConfig, bars: int, beats_per_bar: int, emotion: EmotionState) -> list[SegmentNote]:
        drum_notes = getattr(track, "drum_notes", {}) or {}
        result: list[SegmentNote] = []
        for bar in range(bars):
            for local_beat in range(beats_per_bar):
                absolute = bar * beats_per_bar + local_beat
                pitches = [drum_notes.get("kick", 36)] if local_beat in {0, 2} else []
                if local_beat in {1, 3} and emotion.arousal_norm >= 0.42:
                    pitches.append(drum_notes.get("snare", 38))
                if emotion.arousal_norm >= 0.62:
                    pitches.append(drum_notes.get("closed_hat", 42))
                for pitch in pitches:
                    result.append(SegmentNote(
                        beat=absolute,
                        duration_beats=0.2,
                        pitch=pitch,
                        velocity=round(55 + emotion.arousal_norm * 45),
                        track_id=track.id,
                        channel=track.midi_channel,
                    ))
        return result

    def _cymbals(
        self,
        track: TrackConfig,
        emotion: EmotionState,
        previous_emotion: EmotionLabel,
        bars: int,
        beats_per_bar: int,
    ) -> list[SegmentNote]:
        if emotion.label == previous_emotion and emotion.arousal_norm < 0.72:
            return []
        return [SegmentNote(
            beat=0,
            duration_beats=0.35,
            pitch=min(track.pitch_range[1], 49),
            velocity=round(55 + emotion.arousal_norm * 45),
            track_id=track.id,
            channel=track.midi_channel,
        )]

    @staticmethod
    def _track(tracks: list[TrackConfig], role: str) -> TrackConfig:
        track = next((item for item in tracks if item.enabled and item.compute_enabled and item.role == role), None)
        if track is None:
            raise ValueError(f"enabled {role} track is required")
        return track

    @staticmethod
    def _optional_track(tracks: list[TrackConfig], role: str) -> TrackConfig | None:
        return next((item for item in tracks if item.enabled and item.compute_enabled and item.role == role), None)
