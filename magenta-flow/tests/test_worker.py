from pathlib import Path

import numpy as np
import soundfile as sf

from magenta_flow.worker import StemLoopMixer, WorkerControl


def test_stem_loop_mixer_crossfades_and_limits(tmp_path: Path):
    sample_rate = 100
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    sf.write(first, np.full((100, 2), 0.25, dtype=np.float32), sample_rate)
    sf.write(second, np.full((100, 2), -0.25, dtype=np.float32), sample_rate)
    mixer = StemLoopMixer(sample_rate, crossfade_seconds=0.5)
    mixer.load(str(first))
    before = mixer.mix(np.zeros((20, 2), dtype=np.float32), 1.0)
    mixer.load(str(second))
    during = mixer.mix(np.zeros((20, 2), dtype=np.float32), 1.0)
    after = mixer.mix(np.zeros((60, 2), dtype=np.float32), 1.0)
    assert np.mean(before) > 0.2
    assert np.mean(during) > -0.2
    assert np.mean(after[-10:]) < -0.2
    assert np.max(np.abs(after)) <= 0.98


def test_worker_control_defaults_to_low_gain_optional_audio():
    control = WorkerControl()
    assert control.audio_enabled
    assert control.audio_gain == 0.2
    assert control.stem_gain == 0.0
