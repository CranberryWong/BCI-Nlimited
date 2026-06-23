from __future__ import annotations

import random
import time

from app.music.midi_output import MidiOutput
from app.music.osc_output import OscOutput
from app.music.scales import choose_quantized, resolve_scale, root_pc, scale_notes, enumerate_scale_sequence
from app.music.schemas import ActiveMusicConfig, EmotionState, MusicEvent, TrackConfig
from collections import defaultdict

class MusicEngine:
    def __init__(self, config: ActiveMusicConfig, midi: MidiOutput, osc: OscOutput) -> None:
        self.config = config
        self.midi = midi
        self.osc = osc
        self.last_arousal = 0.0
        self.last_label = "neutral"
        self.sequence_index: dict[str, int] = defaultdict(int)

    def update_config(self, config: ActiveMusicConfig) -> None:
        self.config = config

    def generate(self, emotion: EmotionState) -> list[MusicEvent]:
        events: list[MusicEvent] = []
        for track in self.config.tracks:
            if not track.enabled or not track.compute_enabled:
                continue
            profile = self.config.emotion_profiles[emotion.label]
            density = self._density(track, emotion)
            if track.role not in {"pad", "chord"} and random.random() > density:
                continue
            if track.role == "melody":
                # 新增模式切换：若 play_mode 为 "sequence"，使用预定义序列
                if getattr(track, "play_mode", "emotion") == "sequence":
                    events.extend(self._melody_sequence(track))
                    continue
                else:
                    events.extend(self._melody(track, emotion))
         
            elif track.role == "chord":
                events.extend(self._chord(track, emotion))
            elif track.role == "bass":
                events.extend(self._bass(track, emotion))
            elif track.role == "drum":
                events.extend(self._drums(track, emotion))
            elif track.role == "cymbal":
                events.extend(self._cymbal(track, emotion))
            elif track.role == "pad":
                events.extend(self._pad(track, emotion))
            elif profile.tension > 0.4:
                events.append(self._control(track, "tension", profile.tension))
            self.osc.send_emotion(track, emotion)
        self.last_arousal = emotion.arousal_norm
        self.last_label = emotion.label
        for event in events:
            track = next(item for item in self.config.tracks if item.id == event.track_id)
            self._dispatch(track, event)
        return events

    # def generate_fixed_sequence(self, track, root_note="C#", scale="pentatonic", low=61, high=94):
    #     notes = enumerate_scale_sequence(root_note, scale, low, high)

    def generate_fixed_sequence(
        self,
        track: TrackConfig,
        root_note: str | None = None,
        scale: str | None = None,
        low: int | None = None,
        high: int | None = None,
        velocity: int | None = None,
    ) -> list[MusicEvent]:
        # 采用 track 配置为默认
        root_note = root_note or getattr(track, "sequence_root_note", self.config.global_settings.root_note)
        scale = scale or getattr(track, "sequence_scale", "major")
        low = low if low is not None else int(getattr(track, "sequence_low", track.pitch_range[0]))
        high = high if high is not None else int(getattr(track, "sequence_high", track.pitch_range[1]))
        velocity = velocity if velocity is not None else max(track.velocity_range[0], min(track.velocity_range[1], 80))

        # 获取确定性音序
        notes = enumerate_scale_sequence(root_note, scale, low, high)

        events: list[MusicEvent] = []
        for pitch in notes:
            events.extend(self._note(track, pitch, velocity, track.note_length_ms))

        return events
    def test_event(self, track: TrackConfig) -> list[MusicEvent]:
        pitch = sum(track.pitch_range) // 2
        events = self._voiced_notes(
            track,
            pitch,
            max(64, track.velocity_range[0]),
            min(360, track.note_length_ms),
        )
        for event in events:
            self._dispatch(track, event)
        return events

    def dispatch_event(self, event: MusicEvent) -> None:
        track = next((item for item in self.config.tracks if item.id == event.track_id), None)
        if track is not None:
            self._dispatch(track, event)

    def all_notes_off(self) -> None:
        self.midi.all_notes_off()
        self.osc.all_notes_off(self.config.tracks)

    def _dispatch(self, track: TrackConfig, event: MusicEvent) -> None:
        mode = self.config.global_settings.output_mode
        if mode == "mock":
            return
        if track.output_type == "osc" and mode in {"osc", "both"}:
            self.osc.send_event(track, event)
        if track.output_type == "midi" and mode in {"midi", "both"}:
            self.midi.send_event(track, event)

    def _melody(self, track: TrackConfig, emotion: EmotionState) -> list[MusicEvent]:
        randomness = self._randomness(track, emotion)
        pitch = self._pitch(track, emotion, randomness)
        velocity = self._velocity(track, emotion)
        return self._voiced_notes(track, pitch, velocity, track.note_length_ms, emotion)

    def _melody_sequence(self, track: TrackConfig) -> list[MusicEvent]:
        root_note = getattr(track, "sequence_root_note", self.config.global_settings.root_note)
        scale = getattr(track, "sequence_scale", "major")
        low = int(getattr(track, "sequence_low", track.pitch_range[0]))
        high = int(getattr(track, "sequence_high", track.pitch_range[1]))
        notes = enumerate_scale_sequence(root_note, scale, low, high)
        if not notes:
            return []

        # 获取当前索引音
        idx = self.sequence_index[track.id]
        pitch = notes[idx % len(notes)]
        self.sequence_index[track.id] = idx + 1

        velocity = max(track.velocity_range[0], min(track.velocity_range[1], 80))
        return self._voiced_notes(track, pitch, velocity, track.note_length_ms)
    
    def _chord(self, track: TrackConfig, emotion: EmotionState) -> list[MusicEvent]:
        root = self._pitch(track, emotion, self._randomness(track, emotion) / 2)
        qualities = {
            "joy": (0, 4, 7),
            "sad": (0, 3, 7),
            "tense": (0, 3, 6, 11),
            "calm": (0, 7, 14),
            "neutral": (0, 4, 7),
        }
        pitches = self._chord_pitches(track, root, qualities[emotion.label])
        return self._notes(track, pitches, self._velocity(track, emotion), track.note_length_ms)

    def _bass(self, track: TrackConfig, emotion: EmotionState) -> list[MusicEvent]:
        root = root_pc(track.root_note, self.config.global_settings.root_note)
        notes = scale_notes(root, "minor" if emotion.label == "sad" else "major", *track.pitch_range) or [track.pitch_range[0]]
        pitch = notes[0] if emotion.arousal_norm < 0.65 or random.random() < 0.65 else self._clamp_pitch(track, notes[0] + 7)
        duration = track.note_length_ms * (2 if emotion.label in {"sad", "calm"} else 1)
        return self._voiced_notes(track, pitch, self._velocity(track, emotion), duration, emotion)

    def _drums(self, track: TrackConfig, emotion: EmotionState) -> list[MusicEvent]:
        notes = getattr(track, "drum_notes", {}) or {}
        hits = [notes.get("kick", 36)]
        if emotion.arousal_norm > 0.45:
            hits.append(notes.get("closed_hat", 42))
        if emotion.arousal_norm > 0.68 and random.random() < emotion.arousal_norm:
            hits.append(notes.get("snare", 38))
        return [event for pitch in hits for event in self._note(track, pitch, self._velocity(track, emotion), track.note_length_ms)]

    def _cymbal(self, track: TrackConfig, emotion: EmotionState) -> list[MusicEvent]:
        rise = emotion.arousal_norm - self.last_arousal
        threshold = float(getattr(track, "arousal_rise_threshold", 0.18))
        changed = emotion.label != self.last_label
        if getattr(track, "trigger_on_arousal_rise", True) and (rise >= threshold or changed):
            return self._note(track, min(track.pitch_range[1], 49), self._velocity(track, emotion), track.note_length_ms)
        if emotion.arousal_norm > 0.72:
            return self._note(track, min(track.pitch_range[1], 42), self._velocity(track, emotion), track.note_length_ms)
        return []

    def _pad(self, track: TrackConfig, emotion: EmotionState) -> list[MusicEvent]:
        events = self._chord(track, emotion)
        if emotion.confidence < 0.65:
            events.append(self._control(track, "reverb", round(1 - emotion.confidence, 3)))
            events.append(self._control(track, "filter", round(0.35 + emotion.valence_norm * 0.4, 3)))
        return events

    def _pitch(self, track: TrackConfig, emotion: EmotionState, randomness: float) -> int:
        profile = self.config.emotion_profiles[emotion.label]
        root = root_pc(track.root_note, self.config.global_settings.root_note)
        scale = resolve_scale(track.scale, profile.scale, self.config.global_settings.scale, emotion.label)
        position = 0.5 + (emotion.valence_norm - 0.5) * track.mapping.valence_to_pitch
        return choose_quantized(root, scale, *track.pitch_range, position, randomness)

    def _velocity(self, track: TrackConfig, emotion: EmotionState) -> int:
        low, high = track.velocity_range
        position = max(0.0, min(1.0, 0.5 + (emotion.arousal_norm - 0.5) * track.mapping.arousal_to_velocity))
        return max(1, min(127, round((low + (high - low) * position) * self.config.global_settings.master_velocity)))

    def _density(self, track: TrackConfig, emotion: EmotionState) -> float:
        base = track.density
        arousal_gain = (emotion.arousal_norm - 0.5) * track.mapping.arousal_to_density
        density = (base + arousal_gain) * self.config.global_settings.master_density

        if track.role == "drum":
            density *= 1.3
        elif track.role == "cymbal":
            density *= 1.2
        elif track.role == "pad":
            density *= 0.5

        return max(0.12, min(1.0, density))

    @staticmethod
    def _randomness(track: TrackConfig, emotion: EmotionState) -> float:
        base = 1 - emotion.confidence
        mapped = base + track.mapping.probability_to_randomness * emotion.confidence
        return max(0.0, min(1.0, mapped))

    @staticmethod
    def _clamp_pitch(track: TrackConfig, pitch: int) -> int:
        return max(track.pitch_range[0], min(track.pitch_range[1], pitch))

    def _note(self, track: TrackConfig, pitch: int, velocity: int, duration: int) -> list[MusicEvent]:
        start = time.time() + track.delay_ms / 1000 + random.uniform(-1, 1) * track.humanize * 0.03
        return [
            MusicEvent(timestamp=start, track_id=track.id, type="note_on", pitch=pitch, velocity=velocity, duration_ms=duration, channel=track.midi_channel),
            MusicEvent(timestamp=start + duration / 1000, track_id=track.id, type="note_off", pitch=pitch, velocity=0, duration_ms=0, channel=track.midi_channel),
        ]

    def _voiced_notes(
        self,
        track: TrackConfig,
        base_pitch: int,
        velocity: int,
        duration: int,
        emotion: EmotionState | None = None,
    ) -> list[MusicEvent]:
        pitches = self._scale_voicing(track, base_pitch, emotion)
        return self._notes(track, pitches, velocity, duration)

    def _scale_voicing(
        self,
        track: TrackConfig,
        base_pitch: int,
        emotion: EmotionState | None = None,
    ) -> list[int]:
        count = max(1, int(track.polyphony))
        if count == 1 or track.role in {"drum", "cymbal", "fx"}:
            return [self._clamp_pitch(track, base_pitch)]

        profile_scale = self.config.emotion_profiles[emotion.label].scale if emotion else "major"
        label = emotion.label if emotion else "neutral"
        root = root_pc(track.root_note, self.config.global_settings.root_note)
        scale = resolve_scale(track.scale, profile_scale, self.config.global_settings.scale, label)
        available = scale_notes(root, scale, *track.pitch_range) or list(range(track.pitch_range[0], track.pitch_range[1] + 1))
        base_index = min(range(len(available)), key=lambda index: abs(available[index] - base_pitch))

        if track.role == "bass":
            desired = [base_pitch, base_pitch + 7, base_pitch + 12, base_pitch + 19, base_pitch + 24]
            pitches = self._nearest_unique(available, desired, count)
        else:
            # Scale thirds above and below the source note produce a fuller,
            # harmonically related voicing without changing onset density.
            offsets = [0, 2, -2, 4, -4, 6, -6, 8, -8, 10, -10, 12, -12]
            pitches = []
            for offset in offsets:
                index = base_index + offset
                if 0 <= index < len(available) and available[index] not in pitches:
                    pitches.append(available[index])
                if len(pitches) >= count:
                    break
        return sorted(pitches[:count]) or [self._clamp_pitch(track, base_pitch)]

    def _chord_pitches(self, track: TrackConfig, root: int, intervals: tuple[int, ...]) -> list[int]:
        count = max(1, int(track.polyphony))
        candidates: list[int] = []
        for octave in (0, 12, -12, 24, -24):
            for interval in intervals:
                pitch = root + interval + octave
                if track.pitch_range[0] <= pitch <= track.pitch_range[1] and pitch not in candidates:
                    candidates.append(pitch)
        if len(candidates) < count:
            candidates.extend(
                pitch
                for pitch in self._scale_voicing(track, root)
                if pitch not in candidates
            )
        return sorted(candidates[:count]) or [self._clamp_pitch(track, root)]

    @staticmethod
    def _nearest_unique(available: list[int], desired: list[int], count: int) -> list[int]:
        pitches: list[int] = []
        for target in desired:
            choices = [pitch for pitch in available if pitch not in pitches]
            if not choices:
                break
            pitches.append(min(choices, key=lambda pitch: abs(pitch - target)))
            if len(pitches) >= count:
                break
        return pitches

    def _notes(self, track: TrackConfig, pitches: list[int], velocity: int, duration: int) -> list[MusicEvent]:
        return [
            event
            for pitch in pitches
            for event in self._note(track, pitch, velocity, duration)
        ]

    @staticmethod
    def _control(track: TrackConfig, name: str, value: float) -> MusicEvent:
        return MusicEvent(track_id=track.id, type="control", address=f"/music/track/{track.id}/control", args=[name, value], channel=track.midi_channel)
