from __future__ import annotations

import numpy as np
import pytest

from magenta_flow.pipeline import prepare_audio_block


def test_prepare_audio_block_makes_transposed_mrt2_output_contiguous():
    channel_first = np.zeros((2, 1_920), dtype=np.float32)
    mrt2_view = channel_first.T
    assert not mrt2_view.flags.c_contiguous

    prepared = prepare_audio_block(mrt2_view, (1_920, 2))

    assert prepared.flags.c_contiguous
    assert prepared.dtype == np.float32
    assert prepared.shape == (1_920, 2)


def test_prepare_audio_block_rejects_unexpected_model_shape():
    with pytest.raises(ValueError, match="MRT2 returned"):
        prepare_audio_block(np.zeros((960, 2), dtype=np.float32), (1_920, 2))
