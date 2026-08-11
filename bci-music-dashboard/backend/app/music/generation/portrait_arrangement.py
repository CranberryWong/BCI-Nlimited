"""Arrangement rules that make Portrait assets behave as one evolving piece."""

from __future__ import annotations

from dataclasses import dataclass

from app.music.generation.portrait_harmony import HarmonyChord
from app.music.generation.portrait_library import PortraitAsset
from app.music.schemas import SegmentNote, TrackConfig


@dataclass(frozen=True)
class PortraitArrangement:
    tempo_multiplier: float
    role_density: dict[str, float]
    motif_direction: int
    motif_duration: float


class PortraitArranger:
    """Adds a stable bass foundation and a small shared identity cell."""

    PROFILES = {
        "sad": PortraitArrangement(.65, {"pad": .65, "bass": .5, "drum": 0, "cymbal": 0}, -1, .6),
        "calm": PortraitArrangement(.75, {"pad": .8, "bass": .55, "drum": .15, "cymbal": .1}, 1, .65),
        "neutral": PortraitArrangement(.85, {"pad": .85, "bass": .8, "drum": .55, "cymbal": .3}, 1, .4),
        "joy": PortraitArrangement(1.0, {"pad": .8, "bass": 1, "drum": 1, "cymbal": .75}, 1, .28),
        "tense": PortraitArrangement(1.1, {"pad": .35, "bass": 1, "drum": 1, "cymbal": 1}, 1, .22),
    }
    MAX_BPM_STEP = 8

    def target_bpm(self, base_bpm: int, emotion: str) -> int:
        return max(30, min(220, round(base_bpm * self.PROFILES[emotion].tempo_multiplier)))

    def effective_bpm(self, base_bpm: int, emotion: str, previous_bpm: int | None) -> tuple[int, int]:
        target = self.target_bpm(base_bpm, emotion)
        if previous_bpm is None:
            return target, target
        return max(previous_bpm - self.MAX_BPM_STEP, min(previous_bpm + self.MAX_BPM_STEP, target)), target

    def apply(
        self,
        asset: PortraitAsset,
        notes: list[SegmentNote],
        tracks: dict[str, TrackConfig],
        chords: list[HarmonyChord],
        bpm: int,
    ) -> list[SegmentNote]:
        profile = self.PROFILES[asset.emotion]
        filtered = self._apply_density(notes, tracks, profile)
        bass = tracks.get("bass")
        if bass and profile.role_density["bass"]:
            filtered.extend(self._bass_notes(asset, bass, chords, profile.role_density["bass"]))
        melody = tracks.get("melody")
        if melody:
            filtered.extend(self._identity_cell(asset, melody, filtered, profile, bpm))
        return sorted(filtered, key=lambda note: (note.beat, note.track_id, note.pitch))

    @staticmethod
    def _apply_density(
        notes: list[SegmentNote], tracks: dict[str, TrackConfig], profile: PortraitArrangement) -> list[SegmentNote]:
        role_by_id = {track.id: role for role, track in tracks.items()}
        counters: dict[str, int] = {}
        kept: list[SegmentNote] = []
        for note in notes:
            role = role_by_id.get(note.track_id)
            density = profile.role_density.get(role, 1.0)
            if density >= 1:
                kept.append(note)
                continue
            if density <= 0:
                continue
            index = counters.get(role or "", 0)
            counters[role or ""] = index + 1
            # Deterministic thinning keeps an authored asset recognizable.
            if index % max(1, round(1 / density)) == 0:
                kept.append(note)
        return kept

    @staticmethod
    def _bass_notes(
        asset: PortraitAsset,
        track: TrackConfig,
        chords: list[HarmonyChord],
        density: float,
    ) -> list[SegmentNote]:
        notes: list[SegmentNote] = []
        low, high = track.pitch_range
        for bar, chord in enumerate(chords[:asset.bars]):
            root = PortraitArranger._register_pitch(chord.root_pitch_class, low, high)
            if root is None:
                continue
            beat = float(bar * asset.beats_per_bar)
            notes.append(SegmentNote(
                beat=beat,
                duration_beats=min(1.5, asset.beats_per_bar * .7),
                pitch=root,
                velocity=max(track.velocity_range[0], min(track.velocity_range[1], 70)),
                track_id=track.id,
                channel=track.midi_channel,
                generated_by="rule",
                notochord_eligible=True,
            ))
            if density >= .75 and asset.beats_per_bar >= 4:
                fifth = PortraitArranger._register_pitch((chord.root_pitch_class + 7) % 12, low, high)
                if fifth is not None:
                    notes.append(SegmentNote(
                        beat=beat + asset.beats_per_bar / 2,
                        duration_beats=.75,
                        pitch=fifth,
                        velocity=max(track.velocity_range[0], min(track.velocity_range[1], 62)),
                        track_id=track.id,
                        channel=track.midi_channel,
                        generated_by="rule",
                        notochord_eligible=True,
                    ))
        return notes

    @staticmethod
    def _identity_cell(
        asset: PortraitAsset,
        track: TrackConfig,
        notes: list[SegmentNote],
        profile: PortraitArrangement,
        bpm: int,
    ) -> list[SegmentNote]:
        """A 1-2-5 cell appears at the final bar when it is safe to strike."""
        low, high = track.pitch_range
        root = asset.home_key
        roots = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
        base = roots.get(root, 0)
        pcs = (base, (base + 2 * profile.motif_direction) % 12, (base + 7 * profile.motif_direction) % 12)
        start = max(0.0, asset.bars * asset.beats_per_bar - min(1.5, asset.beats_per_bar))
        interval = .25 if profile.motif_duration <= .3 else .5
        minimum_beats = asset.same_key_minimum_interval_seconds * bpm / 60.0
        existing = [note for note in notes if note.track_id == track.id]
        additions: list[SegmentNote] = []
        for index, pc in enumerate(pcs):
            beat = round(start + index * interval, 3)
            pitch = PortraitArranger._register_pitch(pc, low, high, prefer_high=True)
            if pitch is None or beat >= asset.bars * asset.beats_per_bar:
                continue
            if any(note.pitch == pitch and abs(note.beat - beat) < minimum_beats for note in existing + additions):
                continue
            additions.append(SegmentNote(
                beat=beat,
                duration_beats=profile.motif_duration,
                pitch=pitch,
                velocity=max(track.velocity_range[0], min(track.velocity_range[1], 58)),
                track_id=track.id,
                channel=track.midi_channel,
                generated_by="rule",
                notochord_eligible=True,
            ))
        return additions

    @staticmethod
    def _register_pitch(pitch_class: int, low: int, high: int, prefer_high: bool = False) -> int | None:
        candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 == pitch_class]
        if not candidates:
            return None
        return candidates[-1] if prefer_high else candidates[0]
