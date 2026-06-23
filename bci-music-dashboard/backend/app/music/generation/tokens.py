from __future__ import annotations

from app.music.schemas import EmotionLabel, SegmentNote


PAD, BOS, EOS = 0, 1, 2
EMOTION_BASE = 10
PREVIOUS_EMOTION_BASE = 20
BPM_BASE = 32
BAR_BASE = 96
POSITION_BASE = 112
PITCH_BASE = 160
DURATION_BASE = 288
VELOCITY_BASE = 320
VOCAB_SIZE = 512
EMOTIONS: list[EmotionLabel] = ["joy", "calm", "neutral", "tense", "sad"]


def prompt_tokens(emotion: EmotionLabel, previous: EmotionLabel, bpm: int) -> list[int]:
    return [
        BOS,
        EMOTION_BASE + EMOTIONS.index(emotion),
        PREVIOUS_EMOTION_BASE + EMOTIONS.index(previous),
        BPM_BASE + max(0, min(63, round((bpm - 30) / 3))),
    ]


def encode_notes(
    notes: list[SegmentNote],
    emotion: EmotionLabel,
    previous: EmotionLabel,
    bpm: int,
    beats_per_bar: int = 4,
) -> list[int]:
    result = prompt_tokens(emotion, previous, bpm)
    for note in sorted(notes, key=lambda item: item.beat):
        bar = min(15, int(note.beat // beats_per_bar))
        position = min(47, round((note.beat % beats_per_bar) * 12))
        duration = min(31, max(0, round(note.duration_beats * 4) - 1))
        velocity = min(15, max(0, note.velocity // 8))
        result.extend([
            BAR_BASE + bar,
            POSITION_BASE + position,
            PITCH_BASE + note.pitch,
            DURATION_BASE + duration,
            VELOCITY_BASE + velocity,
        ])
    result.append(EOS)
    return result


def decode_tokens(
    tokens: list[int],
    track_id: str,
    channel: int,
    bars: int = 4,
    beats_per_bar: int = 4,
) -> list[SegmentNote]:
    notes: list[SegmentNote] = []
    state: dict[str, int] = {}
    for token in tokens:
        if token == EOS:
            break
        if BAR_BASE <= token < BAR_BASE + 16:
            state = {"bar": token - BAR_BASE}
        elif POSITION_BASE <= token < POSITION_BASE + 48 and "bar" in state:
            state["position"] = token - POSITION_BASE
        elif PITCH_BASE <= token < PITCH_BASE + 128 and "position" in state:
            state["pitch"] = token - PITCH_BASE
        elif DURATION_BASE <= token < DURATION_BASE + 32 and "pitch" in state:
            state["duration"] = token - DURATION_BASE
        elif VELOCITY_BASE <= token < VELOCITY_BASE + 16 and "duration" in state:
            beat = state["bar"] * beats_per_bar + state["position"] / 12
            if state["bar"] < bars:
                notes.append(SegmentNote(
                    beat=beat,
                    duration_beats=(state["duration"] + 1) / 4,
                    pitch=state["pitch"],
                    velocity=max(1, min(127, (token - VELOCITY_BASE) * 8 + 4)),
                    track_id=track_id,
                    channel=channel,
                ))
            state = {}
    return notes
