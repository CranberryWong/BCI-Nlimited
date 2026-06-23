from __future__ import annotations

import argparse
import json
import random

from common import CHECKPOINT_DIR, PROCESSED_DIR, load_jsonl
from app.music.generation.network import MelodyTransformer, require_torch
from app.music.generation.tokens import PAD, VOCAB_SIZE


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the local emotion-conditioned melody model.")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    torch = require_torch()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = load_jsonl(PROCESSED_DIR / "train.jsonl")
    if not rows:
        raise SystemExit("training_data/processed/train.jsonl contains no samples")
    config = {
        "vocab_size": VOCAB_SIZE,
        "d_model": 256,
        "nhead": 8,
        "layers": 6,
        "max_length": 2048,
        "dropout": 0.1,
    }
    model = MelodyTransformer(**config)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for epoch in range(args.epochs):
        random.shuffle(rows)
        losses = []
        for offset in range(0, len(rows), args.batch_size):
            sequences = [row["tokens"][: config["max_length"]] for row in rows[offset:offset + args.batch_size]]
            width = max(len(item) for item in sequences)
            batch = torch.full((len(sequences), width), PAD, dtype=torch.long)
            for index, sequence in enumerate(sequences):
                batch[index, :len(sequence)] = torch.tensor(sequence)
            batch = batch.to(device)
            logits = model(batch[:, :-1])
            loss = torch.nn.functional.cross_entropy(
                logits.reshape(-1, logits.shape[-1]),
                batch[:, 1:].reshape(-1),
                ignore_index=PAD,
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        mean_loss = sum(losses) / len(losses)
        checkpoint = CHECKPOINT_DIR / f"epoch-{epoch + 1:03d}.pt"
        torch.save({"model_state": model.state_dict(), "model": config, "epoch": epoch + 1, "loss": mean_loss}, checkpoint)
        (CHECKPOINT_DIR / "training_config.json").write_text(
            json.dumps({"model": config, "device": device, "last_epoch": epoch + 1, "loss": mean_loss}, indent=2),
            encoding="utf-8",
        )
        print(f"epoch={epoch + 1} loss={mean_loss:.4f} device={device}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
