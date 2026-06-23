# Melody Training Data

Place licensed, human-reviewed MIDI files into exactly one emotion folder:

- `joy`
- `calm`
- `neutral`
- `tense`
- `sad`

Each file must contain one non-drum melody track in 4/4. Raw MIDI files and
processed datasets are intentionally ignored by Git. Keep provenance and
license records outside the MIDI file or in a neighboring private data
inventory.

Run the workflow from the project root:

```bash
python scripts/music_training/validate_dataset.py
python scripts/music_training/prepare_dataset.py
python scripts/music_training/train_melody.py --epochs 1
python scripts/music_training/evaluate_melody.py
python scripts/music_training/export_model.py
```
