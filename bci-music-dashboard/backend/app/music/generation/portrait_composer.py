"""Map authored portrait MIDI tracks directly to the active output tracks."""

from __future__ import annotations

import time
import uuid

from app.music.generation.form import FormPosition
from app.music.generation.portrait_arrangement import PortraitArranger
from app.music.generation.portrait_harmony import PortraitHarmonyPlanner
from app.music.generation.portrait_library import PortraitAsset
from app.music.schemas import EmotionState, MusicSegment, SegmentNote, TrackConfig


class PortraitComposer:
    TRACK_ROLES = {"Xylophone": "melody", "Electronic": "pad", "Drums": "drum", "Cymbals": "cymbal"}

    def __init__(self) -> None:
        self.harmony_planner = PortraitHarmonyPlanner()
        self.arranger = PortraitArranger()

    def compose(
        self,
        asset: PortraitAsset,
        position: FormPosition,
        emotion: EmotionState,
        previous_emotion: str,
        tracks: list[TrackConfig],
        *,
        bpm: int | None = None,
        harmony_enabled: bool = False,
        harmony_arpeggio_enabled: bool = False,
    ) -> MusicSegment:
        started = time.perf_counter()
        by_role = {track.role: track for track in tracks if track.enabled and track.compute_enabled}
        if "pad" not in by_role and "chord" in by_role:
            by_role["pad"] = by_role["chord"]
        notes: list[SegmentNote] = []
        for source in asset.notes:
            role = self.TRACK_ROLES.get(source.source_track)
            track = by_role.get(role) if role else None
            if track is None:
                continue
            # Portrait assets are already composed for the physical xylophone.
            # Do not fold their low/high notes into the legacy melody track range:
            # that would turn distinct keys into the same retriggered MIDI pitch.
            low, high = track.pitch_range
            pitch = source.pitch if role == "melody" else max(low, min(high, source.pitch))
            velocity = max(track.velocity_range[0], min(track.velocity_range[1], source.velocity))
            notes.append(SegmentNote(
                beat=source.beat, duration_beats=source.duration_beats, pitch=pitch, velocity=velocity,
                track_id=track.id, channel=track.midi_channel,
                voice_role="theme" if role == "melody" else None, generated_by="rule",
            ))
        playback_bpm = bpm or asset.bpm
        melody_track = by_role.get("melody")
        chords = self.harmony_planner.harmony_for(asset)
        notes = self.arranger.apply(asset, notes, by_role, chords, playback_bpm)
        harmony = [chord.label for chord in chords]
        if harmony_enabled:
            notes, _ = self.harmony_planner.apply(
                asset,
                notes,
                melody_track,
                playback_bpm,
                arpeggio_enabled=harmony_arpeggio_enabled,
            )
        xylophone = [note for note in notes if note.voice_role in {"theme", "harmony"}]
        max_voices = max((sum(1 for other in xylophone if abs(other.beat - note.beat) < .01) for note in xylophone), default=1)
        return MusicSegment(
            id=uuid.uuid4().hex[:12], emotion=emotion.label, previous_emotion=previous_emotion,
            bpm=playback_bpm, bars=asset.bars, beats_per_bar=asset.beats_per_bar,
            root_note=asset.home_key, scale=asset.mode, source="portrait", form_section=position.section,
            phrase_id=position.phrase_id, portrait=asset.emotion, portrait_asset_id=asset.id,
            portrait_asset_title=asset.title, portrait_role=asset.role, theme_similarity=0.0,
            harmony=harmony, transition_type="continue", actual_max_voices=max_voices,
            harmony_note_count=sum(note.voice_role == "harmony" for note in notes),
            arpeggio_note_count=sum(note.voice_role == "ornament" for note in notes),
            bass_note_count=sum(note.track_id == by_role["bass"].id for note in notes if "bass" in by_role),
            drum_note_count=sum(note.track_id == by_role["drum"].id for note in notes if "drum" in by_role),
            cymbal_note_count=sum(note.track_id == by_role["cymbal"].id for note in notes if "cymbal" in by_role),
            generation_ms=(time.perf_counter() - started) * 1000,
            notes=sorted(notes, key=lambda note: (note.beat, note.track_id, note.pitch)),
        )
