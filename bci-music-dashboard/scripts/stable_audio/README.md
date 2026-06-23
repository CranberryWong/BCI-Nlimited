# Stable Audio Open local test

Run from the project root:

```bash
.venv-stable-audio/bin/python scripts/stable_audio/generate.py
```

The first run downloads the gated model from Hugging Face. Generated WAV files
are written to `generated_audio/`.

Start with a short CPU test:

```bash
.venv-stable-audio/bin/python scripts/stable_audio/generate.py \
  --device cpu \
  --seconds 5 \
  --steps 30 \
  --prompt "soft Chinese wooden percussion, sparse calm ambience, no vocals"
```
