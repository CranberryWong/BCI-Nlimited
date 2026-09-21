from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import librosa
import numpy as np


@dataclass(frozen=True)
class NoteEvent:
    """A real-time, monophonic MIDI event produced from audio."""

    kind: str
    note: int
    velocity: int
    timestamp: float
    frequency: float | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class PitchObservation:
    """One audio-frame observation passed to the note state machine."""

    note: int | None
    frequency: float | None
    confidence: float
    rms_db: float
    onset: bool


@dataclass(frozen=True)
class TranscriberConfig:
    sample_rate: int = 48_000
    block_size: int = 1_920
    analysis_window: int = 4_096
    fmin_midi: int = 48  # C3
    fmax_midi: int = 96  # C7
    silence_db: float = -45.0
    pitch_confidence: float = 0.42
    stable_frames: int = 2
    silence_frames: int = 2
    min_retrigger_seconds: float = 0.08
    minimum_note_seconds: float = 0.08
    onset_flux_floor: float = 0.025
    onset_rms_rise_db: float = 2.5

    @property
    def fmin_hz(self) -> float:
        return float(librosa.midi_to_hz(self.fmin_midi))

    @property
    def fmax_hz(self) -> float:
        return float(librosa.midi_to_hz(self.fmax_midi))


class MonophonicEventTracker:
    """Turns pitch observations into a strictly monophonic event stream."""

    def __init__(self, config: TranscriberConfig):
        self.config = config
        self.active_note: int | None = None
        self._pending_note: int | None = None
        self._pending_count = 0
        self._silence_count = 0
        self._last_trigger_time = -math.inf

    def process(
        self, observation: PitchObservation, timestamp: float
    ) -> list[NoteEvent]:
        events: list[NoteEvent] = []
        note = observation.note

        if note is None or observation.rms_db < self.config.silence_db:
            self._pending_note = None
            self._pending_count = 0
            self._silence_count += 1
            if (
                self.active_note is not None
                and self._silence_count >= self.config.silence_frames
                and timestamp - self._last_trigger_time + 1e-9 >= self.config.minimum_note_seconds
            ):
                events.append(self._note_off(self.active_note, timestamp))
                self.active_note = None
            return events

        self._silence_count = 0
        if note == self._pending_note:
            self._pending_count += 1
        else:
            self._pending_note = note
            self._pending_count = 1

        stable = self._pending_count >= self.config.stable_frames
        if not stable:
            return events

        if self.active_note is None:
            events.append(self._note_on(note, observation, timestamp))
            self.active_note = note
            self._last_trigger_time = timestamp
            return events

        if note != self.active_note:
            if timestamp - self._last_trigger_time + 1e-9 < self.config.minimum_note_seconds:
                return events
            events.append(self._note_off(self.active_note, timestamp))
            events.append(self._note_on(note, observation, timestamp))
            self.active_note = note
            self._last_trigger_time = timestamp
            return events

        if (
            observation.onset
            and timestamp - self._last_trigger_time
            >= self.config.min_retrigger_seconds
        ):
            # A marimba can strike the same bar repeatedly. Explicitly close the
            # current note first so downstream MIDI remains monophonic.
            events.append(self._note_off(note, timestamp))
            events.append(self._note_on(note, observation, timestamp))
            self._last_trigger_time = timestamp

        return events

    def flush(self, timestamp: float) -> list[NoteEvent]:
        if self.active_note is None:
            return []
        event = self._note_off(self.active_note, timestamp)
        self.active_note = None
        self._pending_note = None
        self._pending_count = 0
        return [event]

    @staticmethod
    def _note_off(note: int, timestamp: float) -> NoteEvent:
        return NoteEvent("note_off", note, 0, timestamp)

    @staticmethod
    def _note_on(
        note: int, observation: PitchObservation, timestamp: float
    ) -> NoteEvent:
        velocity = int(
            np.clip(
                round(np.interp(observation.rms_db, [-45.0, -6.0], [24, 127])),
                1,
                127,
            )
        )
        return NoteEvent(
            "note_on",
            note,
            velocity,
            timestamp,
            observation.frequency,
            observation.confidence,
        )


class StreamingMonophonicTranscriber:
    """Analyze MRT2's 48 kHz blocks using YIN and adaptive spectral flux."""

    def __init__(self, config: TranscriberConfig | None = None):
        self.config = config or TranscriberConfig()
        self.tracker = MonophonicEventTracker(self.config)
        self._window = np.zeros(self.config.analysis_window, dtype=np.float32)
        self._previous_spectrum: np.ndarray | None = None
        self._previous_rms_db = -120.0
        self._flux_history: deque[float] = deque(maxlen=12)
        self._pitch_history: deque[int] = deque(maxlen=3)

    @property
    def analysis_latency_ms(self) -> float:
        return 1_000.0 * self.config.analysis_window / self.config.sample_rate

    def process_block(
        self, stereo_samples: np.ndarray, timestamp: float
    ) -> list[NoteEvent]:
        mono = self._as_mono(stereo_samples)
        self._append_audio(mono)
        observation = self._observe(mono)
        return self.tracker.process(observation, timestamp)

    def flush(self, timestamp: float) -> list[NoteEvent]:
        return self.tracker.flush(timestamp)

    def _as_mono(self, samples: np.ndarray) -> np.ndarray:
        values = np.asarray(samples, dtype=np.float32)
        if values.ndim == 1:
            mono = values
        elif values.ndim == 2 and values.shape[1] in (1, 2):
            mono = values.mean(axis=1)
        else:
            raise ValueError(f"Expected mono/stereo audio, got {values.shape}")
        if len(mono) != self.config.block_size:
            raise ValueError(
                f"Expected {self.config.block_size} samples, got {len(mono)}"
            )
        return mono

    def _append_audio(self, mono: np.ndarray) -> None:
        shift = len(mono)
        self._window[:-shift] = self._window[shift:]
        self._window[-shift:] = mono

    def _observe(self, current_block: np.ndarray) -> PitchObservation:
        rms = float(np.sqrt(np.mean(np.square(current_block), dtype=np.float64)))
        rms_db = 20.0 * math.log10(max(rms, 1e-8))
        onset = self._detect_onset(current_block, rms_db)

        frequency: float | None = None
        confidence = 0.0
        note: int | None = None
        if rms_db >= self.config.silence_db:
            try:
                estimate = librosa.yin(
                    self._window,
                    fmin=self.config.fmin_hz,
                    fmax=self.config.fmax_hz,
                    sr=self.config.sample_rate,
                    frame_length=self.config.analysis_window,
                    hop_length=self.config.analysis_window,
                    center=False,
                    trough_threshold=0.12,
                )
                candidate = float(estimate[-1])
                if math.isfinite(candidate):
                    confidence = self._periodicity(candidate)
                    if confidence >= self.config.pitch_confidence:
                        raw_note = int(round(float(librosa.hz_to_midi(candidate))))
                        note = self._correct_octave(raw_note, onset)
                        frequency = candidate
            except (ValueError, FloatingPointError):
                pass

        self._previous_rms_db = rms_db
        return PitchObservation(note, frequency, confidence, rms_db, onset)

    def _detect_onset(self, block: np.ndarray, rms_db: float) -> bool:
        windowed = block * np.hanning(len(block)).astype(np.float32)
        spectrum = np.abs(np.fft.rfft(windowed)).astype(np.float32)
        spectrum /= max(float(np.sum(spectrum)), 1e-8)
        if self._previous_spectrum is None:
            flux = 0.0
        else:
            flux = float(np.maximum(spectrum - self._previous_spectrum, 0).sum())
        self._previous_spectrum = spectrum

        history = np.asarray(self._flux_history, dtype=np.float32)
        if len(history) >= 4:
            median = float(np.median(history))
            mad = float(np.median(np.abs(history - median)))
            threshold = max(self.config.onset_flux_floor, median + 3.0 * mad)
        else:
            threshold = self.config.onset_flux_floor
        self._flux_history.append(flux)

        audible_start = (
            self._previous_rms_db < self.config.silence_db
            and rms_db >= self.config.silence_db
        )
        energetic_attack = (
            flux >= threshold
            and rms_db - self._previous_rms_db >= self.config.onset_rms_rise_db
        )
        return audible_start or energetic_attack

    def _periodicity(self, frequency: float) -> float:
        lag = int(round(self.config.sample_rate / frequency))
        if lag <= 0 or lag >= len(self._window) // 2:
            return 0.0
        centered = self._window - float(np.mean(self._window))
        left = centered[:-lag]
        right = centered[lag:]
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 1e-9:
            return 0.0
        return float(np.clip(np.dot(left, right) / denominator, 0.0, 1.0))

    def _correct_octave(self, note: int, onset: bool) -> int:
        note = int(np.clip(note, self.config.fmin_midi, self.config.fmax_midi))
        reference = self.tracker.active_note
        if reference is not None and not onset:
            if abs(note - reference) == 12:
                note = reference

        self._pitch_history.append(note)
        if len(self._pitch_history) >= 2:
            recent = list(self._pitch_history)[-2:]
            if recent[0] == recent[1]:
                return recent[1]
        return note
