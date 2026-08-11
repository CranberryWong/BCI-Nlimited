"""Rule-based xylophone harmony for authored Portrait segments."""

from __future__ import annotations

from dataclasses import dataclass

from app.music.generation.portrait_library import PortraitAsset
from app.music.schemas import SegmentNote, TrackConfig


ROOTS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


@dataclass(frozen=True)
class HarmonyChord:
    label: str
    pitch_classes: frozenset[int]
    root_pitch_class: int


class PortraitHarmonyPlanner:
    """Adds lower xylophone harmony at structurally important melody events."""

    _TEMPLATES = {
        "joy": ("I", "V", "vi", "IV"),
        "calm": ("i", "IV", "VII", "i"),
        "neutral": ("I", "IV", "ii", "V"),
        "tense": ("i", "iv", "V", "i"),
        "sad": ("i", "VI", "III", "VII"),
    }
    _RELEASE_TEMPLATES = {
        "joy": ("I", "IV", "V", "I"),
        "calm": ("i", "IV", "V", "i"),
        "neutral": ("I", "ii", "V", "I"),
        "tense": ("i", "iv", "V", "i"),
        "sad": ("i", "iv", "V", "i"),
    }

    def harmony_for(self, asset: PortraitAsset) -> list[HarmonyChord]:
        symbols = (
            self._RELEASE_TEMPLATES[asset.emotion]
            if asset.role == "release"
            else self._TEMPLATES[asset.emotion]
        )
        return [self._chord(asset.home_key, asset.mode, symbol) for symbol in symbols]

    def apply(
        self,
        asset: PortraitAsset,
        notes: list[SegmentNote],
        melody_track: TrackConfig | None,
        bpm: int,
        arpeggio_enabled: bool = False,
    ) -> tuple[list[SegmentNote], list[str]]:
        chords = self.harmony_for(asset)
        if melody_track is None or not chords:
            return notes, [chord.label for chord in chords]

        melody = [note for note in notes if note.track_id == melody_track.id and note.voice_role == "theme"]
        by_beat: dict[float, list[SegmentNote]] = {}
        for note in melody:
            by_beat.setdefault(round(note.beat, 3), []).append(note)

        additions: list[SegmentNote] = []
        last_added_by_pitch: dict[int, float] = {}
        min_source_pitch = min(
            melody_track.pitch_range[0],
            min((note.pitch for note in melody), default=melody_track.pitch_range[0]),
        )
        minimum_beats = asset.same_key_minimum_interval_seconds * bpm / 60.0
        total_beats = asset.bars * asset.beats_per_bar

        melody_by_beat = sorted(by_beat.items())
        for index, (beat, group) in enumerate(melody_by_beat):
            # Existing authored double-stops take priority over generated harmony.
            if len({note.pitch for note in group}) != 1:
                continue
            lead = group[0]
            if not self._is_harmony_anchor(lead, asset, total_beats):
                continue
            chord = chords[min(int(beat // asset.beats_per_bar), len(chords) - 1)]
            pitch = self._lower_chord_tone(lead.pitch, chord, min_source_pitch)
            if pitch is not None:
                previous = last_added_by_pitch.get(pitch)
                if previous is None or beat - previous >= minimum_beats:
                    additions.append(SegmentNote(
                        beat=lead.beat,
                        duration_beats=lead.duration_beats,
                        pitch=pitch,
                        velocity=max(1, lead.velocity - 16),
                        track_id=lead.track_id,
                        channel=lead.channel,
                        voice_role="harmony",
                        generated_by="rule",
                    ))
                    last_added_by_pitch[pitch] = beat

            if arpeggio_enabled:
                next_beat = melody_by_beat[index + 1][0] if index + 1 < len(melody_by_beat) else None
                for note in self._arpeggio_notes(
                    lead,
                    chord,
                    min_source_pitch,
                    melody_track.pitch_range,
                    next_beat,
                    last_added_by_pitch,
                    minimum_beats,
                ):
                    additions.append(note)
                    last_added_by_pitch[note.pitch] = note.beat

        return sorted(notes + additions, key=lambda note: (note.beat, note.track_id, note.pitch)), [chord.label for chord in chords]

    @staticmethod
    def _is_harmony_anchor(note: SegmentNote, asset: PortraitAsset, total_beats: int) -> bool:
        beat_in_bar = round(note.beat % asset.beats_per_bar, 3)
        is_downbeat = beat_in_bar == 0
        is_long = note.duration_beats >= 1.25
        is_ending = note.beat >= total_beats - asset.beats_per_bar
        return is_downbeat or is_long or is_ending

    @staticmethod
    def _lower_chord_tone(lead_pitch: int, chord: HarmonyChord, low_pitch: int) -> int | None:
        candidates = [
            pitch
            for pitch in range(max(0, low_pitch), lead_pitch - 2)
            if pitch % 12 in chord.pitch_classes
        ]
        return candidates[-1] if candidates else None

    @staticmethod
    def _arpeggio_notes(
        lead: SegmentNote,
        chord: HarmonyChord,
        low_pitch: int,
        pitch_range: tuple[int, int],
        next_beat: float | None,
        last_added_by_pitch: dict[int, float],
        minimum_beats: float,
    ) -> list[SegmentNote]:
        low, high = pitch_range
        search_low = max(0, low, low_pitch, lead.pitch - 12)
        search_high = min(high, lead.pitch - 2)
        pitches = [
            pitch
            for pitch in range(search_low, search_high + 1)
            if pitch % 12 in chord.pitch_classes
        ]
        selected = pitches[-3:]
        if not selected:
            return []

        start = lead.beat + 0.25
        end = lead.beat + max(lead.duration_beats, 0.75)
        if next_beat is not None:
            end = min(end, next_beat - 0.05)
        if end - start < 0.2:
            return []

        interval = 0.25 if end - start >= 0.75 else 0.5
        duration = min(0.35, max(0.2, interval * 0.8))
        notes: list[SegmentNote] = []
        for step, pitch in enumerate(selected):
            beat = round(start + step * interval, 3)
            if beat >= end - 0.05:
                break
            previous = last_added_by_pitch.get(pitch)
            if previous is not None and beat - previous < minimum_beats:
                continue
            notes.append(SegmentNote(
                beat=beat,
                duration_beats=duration,
                pitch=pitch,
                velocity=max(1, lead.velocity - 20),
                track_id=lead.track_id,
                channel=lead.channel,
                voice_role="ornament",
                generated_by="rule",
            ))
        return notes

    @staticmethod
    def _chord(home_key: str, mode: str, symbol: str) -> HarmonyChord:
        root = ROOTS.get(home_key, 0)
        is_minor = mode in {"minor", "dorian", "phrygian"}
        degrees = (
            {
                "i": (0, "min"), "ii": (2, "dim"), "III": (3, "maj"),
                "iv": (5, "min"), "IV": (5, "maj"), "v": (7, "min"),
                "V": (7, "maj"), "VI": (8, "maj"), "VII": (10, "maj"),
            }
            if is_minor
            else {
                "I": (0, "maj"), "ii": (2, "min"), "iii": (4, "min"),
                "IV": (5, "maj"), "V": (7, "maj"), "vi": (9, "min"),
                "vii": (11, "dim"),
            }
        )
        offset, quality = degrees.get(symbol, degrees["i"] if is_minor else degrees["I"])
        chord_root = (root + offset) % 12
        intervals = {"maj": (0, 4, 7), "min": (0, 3, 7), "dim": (0, 3, 6)}[quality]
        suffix = {"maj": "", "min": "m", "dim": "dim"}[quality]
        return HarmonyChord(
            label=f"{home_key if offset == 0 else _note_name(chord_root)}{suffix}",
            pitch_classes=frozenset((chord_root + interval) % 12 for interval in intervals),
            root_pitch_class=chord_root,
        )


def _note_name(pitch_class: int) -> str:
    return ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")[pitch_class]
