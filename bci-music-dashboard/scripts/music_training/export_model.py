from __future__ import annotations

import argparse
import json
import shutil

from common import CHECKPOINT_DIR, PROJECT_DIR
from app.music.generation.composer import EMOTION_SCALES


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the latest checkpoint for dashboard inference.")
    parser.add_argument("--checkpoint", default="")
    args = parser.parse_args()
    candidates = sorted(CHECKPOINT_DIR.glob("epoch-*.pt"))
    source = CHECKPOINT_DIR / args.checkpoint if args.checkpoint else (candidates[-1] if candidates else None)
    if source is None or not source.exists():
        raise SystemExit("no checkpoint found")
    target_dir = PROJECT_DIR / "models" / "music"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target_dir / "latest.pt")
    training_config = json.loads((CHECKPOINT_DIR / "training_config.json").read_text(encoding="utf-8"))
    metadata = {
        **training_config,
        "checkpoint": source.name,
        "emotion_scales": {key: values[0] for key, values in EMOTION_SCALES.items()},
        "bars": 4,
        "beats_per_bar": 4,
    }
    (target_dir / "model_config.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"exported {source} to {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
