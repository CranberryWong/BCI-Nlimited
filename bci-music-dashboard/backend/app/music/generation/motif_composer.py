from __future__ import annotations

import time
import uuid

from app.music.generation.form import FormPosition
from app.music.generation.motif_library import Motif
from app.music.generation.theme_composer import ThemeComposer
from app.music.generation.transition import TransitionPlan
from app.music.generation.voicing import MelodyArpeggioEngine, MelodyVoicingEngine
from app.music.scales import ROOTS
from app.music.schemas import EmotionState, MusicSegment, SegmentNote, TrackConfig


PORTRAIT_DENSITY = {
    "joy": 0.9,
    "calm": 0.45,
    "neutral": 0.65,
    "sad": 0.38,
    "tense": 0.82,
}


class MotifComposer:
    def __init__(self) -> None:
        self.voicing = MelodyVoicingEngine()
        self.arpeggio = MelodyArpeggioEngine()
        self.arranger = ThemeComposer()

    def compose(
        self,
        motif: Motif,
        position: FormPosition,
        emotion: EmotionState,
        previous_emotion: str,
        bpm: int,
        tracks: list[TrackConfig],
        freedom: float,
        transition: TransitionPlan,
    ) -> MusicSegment:
        started = time.perf_counter()
        melody_track = self.arranger._required_track(tracks, "melody")
        melody = self._melody(motif, emotion, melody_track, freedom, transition)
        if motif.performance.get("preserve_polyphony"):
            arpeggiated = melody
        else:
            voiced = self.voicing.apply(
                melody,
                list(motif.harmony),
                motif.home_key,
                motif.beats_per_bar,
                position.section,
                emotion,
                melody_track,
                motif.immutable_beats,
            )
            arpeggiated = self.arpeggio.apply(
                melody,
                voiced,
                list(motif.harmony),
                motif.home_key,
                motif.mode,
                motif.beats_per_bar,
                position.section,
                emotion,
                melody_track,
                motif.immutable_beats,
            )
        notes = list(arpeggiated)
        pseudo = self._pseudo_theme(motif)
        pad = self.arranger._optional_track(tracks, "pad") or self.arranger._optional_track(tracks, "chord")
        if pad:
            notes.extend(self.arranger._pad(pseudo, list(motif.harmony), emotion, position, pad))
        bass = self.arranger._optional_track(tracks, "bass")
        if bass:
            notes.extend(self.arranger._bass(pseudo, list(motif.harmony), emotion, position, bass))
            notes.extend(self._bass_pickup(pseudo, emotion, position, bass, transition))
        drum = self.arranger._optional_track(tracks, "drum")
        if drum:
            notes.extend(self.arranger._drums(pseudo, emotion, position, drum))
            notes.extend(self._drum_fill(pseudo, emotion, drum, transition))
        cymbal = self.arranger._optional_track(tracks, "cymbal")
        if cymbal:
            notes.extend(self.arranger._cymbals(pseudo, emotion, position, cymbal))

        actual_max_voices, harmony_count = self.voicing.metrics(arpeggiated)
        return MusicSegment(
            id=uuid.uuid4().hex[:12],
            emotion=emotion.label,
            previous_emotion=previous_emotion,
            bpm=bpm,
            bars=motif.bars,
            beats_per_bar=motif.beats_per_bar,
            root_note=motif.home_key,
            scale=motif.mode,
            source="motif",
            form_section=position.section,
            phrase_id=position.phrase_id,
            motif_id=motif.id,
            motif_title=motif.title,
            portrait=motif.emotion,
            theme_similarity=0.0,
            harmony=list(motif.harmony),
            transition_type=transition.transition_type,
            from_emotion=transition.from_emotion,
            to_emotion=transition.to_emotion,
            transition_progress=transition.progress,
            transition_strategy=transition.strategy,
            actual_max_voices=actual_max_voices,
            harmony_note_count=harmony_count,
            arpeggio_note_count=self.arpeggio.count(arpeggiated),
            generation_ms=(time.perf_counter() - started) * 1000,
            notes=sorted(notes, key=lambda note: (note.beat, note.track_id, note.pitch)),
        )

    def _melody(
        self,
        motif: Motif,
        emotion: EmotionState,
        track: TrackConfig,
        freedom: float,
        transition: TransitionPlan,
    ) -> list[SegmentNote]:
        allowed = motif.variation_allowed
        preserve = bool(motif.performance.get("preserve_polyphony"))
        transpose_min, transpose_max = allowed.get("transpose", [-2, 2])
        transpose = 0 if preserve else round((emotion.valence_norm - 0.5) * (transpose_max - transpose_min))
        octave_choices = allowed.get("octave_shift", [-12, 12])
        octave = 0
        if preserve:
            octave = 0
        elif emotion.label == "joy" and max(octave_choices) >= 12:
            octave = 12
        elif emotion.label == "sad" and min(octave_choices) <= -12:
            octave = -12
        if transition.preparing and transition.to_emotion in {"joy", "calm"}:
            octave = max(0, octave)
        density = PORTRAIT_DENSITY[emotion.label] * (0.75 + emotion.arousal_norm * 0.35)
        density = min(1.0, max(0.2, density + freedom * 0.12))
        notes: list[SegmentNote] = []
        for index, source in enumerate(motif.notes):
            beat = source.beat
            duration = source.duration_beats
            mutable = round(source.beat, 3) in motif.mutable_beats
            if not preserve and mutable and allowed.get("delete_mutable_notes", True):
                if ((index + round(freedom * 10)) * 31) % 100 > round(density * 100):
                    continue
            if not preserve and mutable and allowed.get("rhythm_compress", True) and emotion.arousal_norm > 0.65:
                duration = max(0.25, duration * 0.72)
            elif not preserve and mutable and allowed.get("rhythm_expand", True) and emotion.label in {"calm", "sad"}:
                duration *= 1.12
            pitch = self._fit_pitch(source.pitch + transpose + octave, track.pitch_range)
            velocity = round(source.velocity * (0.72 + emotion.arousal_norm * 0.4))
            if transition.preparing:
                velocity = round(velocity * 0.9)
            notes.append(SegmentNote(
                beat=beat,
                duration_beats=max(0.18, min(duration, motif.bars * motif.beats_per_bar - beat)),
                pitch=pitch,
                velocity=max(track.velocity_range[0], min(track.velocity_range[1], velocity)),
                track_id=track.id,
                channel=track.midi_channel,
                voice_role="theme",
                generated_by="rule" if preserve else "theme",
            ))
        return sorted(notes, key=lambda note: note.beat)

    @staticmethod
    def _fit_pitch(pitch: int, pitch_range: tuple[int, int]) -> int:
        low, high = pitch_range
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        return max(low, min(high, pitch))

    @staticmethod
    def _pseudo_theme(motif: Motif):
        return type(
            "MotifAsTheme",
            (),
            {
                "id": motif.id,
                "title": motif.title,
                "home_key": motif.home_key,
                "mode": motif.mode,
                "beats_per_bar": motif.beats_per_bar,
                "bars": motif.bars,
                "harmony": motif.harmony,
                "immutable_beats": motif.immutable_beats,
            },
        )()

    def _bass_pickup(self, theme, emotion: EmotionState, position: FormPosition, track: TrackConfig, transition: TransitionPlan) -> list[SegmentNote]:
        if not transition.preparing or position.section in {"intro", "coda"}:
            return []
        root = 48 + ROOTS.get(theme.home_key, 0)
        target = self._fit_pitch(root + (2 if transition.to_emotion in {"joy", "calm"} else -2), track.pitch_range)
        beat = max(0.0, theme.bars * theme.beats_per_bar - 1)
        return [SegmentNote(
            beat=beat,
            duration_beats=0.8,
            pitch=target,
            velocity=round(track.velocity_range[0] + (track.velocity_range[1] - track.velocity_range[0]) * 0.45),
            track_id=track.id,
            channel=track.midi_channel,
        )]

    def _drum_fill(self, theme, emotion: EmotionState, track: TrackConfig, transition: TransitionPlan) -> list[SegmentNote]:
        if not transition.preparing:
            return []
        drum_notes = getattr(track, "drum_notes", {}) or {}
        start = max(0.0, theme.bars * theme.beats_per_bar - 1)
        hits = []
        for offset in (0.0, 0.5):
            hits.append(SegmentNote(
                beat=start + offset,
                duration_beats=0.12,
                pitch=drum_notes.get("snare", 38),
                velocity=round(42 + emotion.arousal_norm * 45),
                track_id=track.id,
                channel=track.midi_channel,
            ))
        return hits
