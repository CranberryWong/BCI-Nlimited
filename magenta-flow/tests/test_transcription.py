from __future__ import annotations

import numpy as np

from magenta_flow.transcription import (
    MonophonicEventTracker,
    PitchObservation,
    StreamingMonophonicTranscriber,
    TranscriberConfig,
)


def observation(note: int | None, *, onset: bool = False, db: float = -18.0):
    return PitchObservation(
        note=note,
        frequency=None if note is None else float(440 * 2 ** ((note - 69) / 12)),
        confidence=0.9 if note is not None else 0.0,
        rms_db=db,
        onset=onset,
    )


def test_tracker_orders_note_off_before_pitch_change_note_on():
    tracker = MonophonicEventTracker(TranscriberConfig())
    assert tracker.process(observation(69), 0.00) == []
    first = tracker.process(observation(69), 0.04)
    assert [(event.kind, event.note) for event in first] == [("note_on", 69)]

    assert tracker.process(observation(72), 0.08) == []
    changed = tracker.process(observation(72), 0.12)
    assert [(event.kind, event.note) for event in changed] == [
        ("note_off", 69),
        ("note_on", 72),
    ]


def test_tracker_retriggers_same_marimba_note_without_overlap():
    tracker = MonophonicEventTracker(TranscriberConfig())
    tracker.process(observation(69), 0.00)
    tracker.process(observation(69), 0.04)
    repeated = tracker.process(observation(69, onset=True), 0.16)
    assert [(event.kind, event.note) for event in repeated] == [
        ("note_off", 69),
        ("note_on", 69),
    ]


def test_tracker_closes_note_after_two_silent_frames():
    tracker = MonophonicEventTracker(TranscriberConfig())
    tracker.process(observation(69), 0.00)
    tracker.process(observation(69), 0.04)
    assert tracker.process(observation(None, db=-80), 0.08) == []
    stopped = tracker.process(observation(None, db=-80), 0.12)
    assert [(event.kind, event.note) for event in stopped] == [("note_off", 69)]


def test_streaming_yin_detects_a4_from_generated_audio():
    config = TranscriberConfig()
    transcriber = StreamingMonophonicTranscriber(config)
    phase = 0
    events = []
    for index in range(8):
        positions = np.arange(config.block_size) + phase
        envelope = np.exp(-positions % config.block_size / (config.sample_rate * 0.25))
        mono = (0.5 * envelope * np.sin(2 * np.pi * 440 * positions / config.sample_rate)).astype(np.float32)
        stereo = np.column_stack([mono, mono])
        events.extend(transcriber.process_block(stereo, index / 25))
        phase += config.block_size
    assert any(event.kind == "note_on" and event.note == 69 for event in events)


def test_transcriber_accepts_non_contiguous_mrt2_style_stereo_view():
    config = TranscriberConfig()
    transcriber = StreamingMonophonicTranscriber(config)
    channel_first = np.zeros((2, config.block_size), dtype=np.float32)
    stereo_view = channel_first.T
    assert not stereo_view.flags.c_contiguous
    assert transcriber.process_block(stereo_view, 0.0) == []


def test_tracker_never_has_more_than_one_active_note():
    tracker = MonophonicEventTracker(TranscriberConfig())
    active: set[int] = set()
    all_events = []
    time = 0.0
    for note in (60, 64, 67, 72):
        all_events.extend(tracker.process(observation(note), time))
        time += 0.04
        all_events.extend(tracker.process(observation(note), time))
        time += 0.04
    for event in all_events:
        if event.kind == "note_on":
            active.add(event.note)
        else:
            active.discard(event.note)
        assert len(active) <= 1
