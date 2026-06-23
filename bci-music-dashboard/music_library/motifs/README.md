# Motif Library

Short portrait motifs live under one emotion folder per approved label:

```text
motifs/
  joy/
    joy_001.mid
    joy_001.yaml
  calm/
  neutral/
  sad/
  tense/
```

Runtime MIDI files contain one non-overlapping melody line only. YAML files
contain metadata, licensing, phrase anchors, harmony, portrait behavior, and
review status. If you pass a polyphonic transcription or a long Lyria-derived
MIDI to the analyzer, it auto-extracts the highest melody line into
`*_melody.mid` and writes a matching `*_melody.yaml`.

Generate a draft YAML from a corrected MIDI file:

```bash
python scripts/music_library/analyze_motif.py music_library/motifs/joy/joy_001.mid --emotion joy --title "Bright Motif"
```

For strict production checks, add `--strict-single-melody` to reject polyphonic
or overlapping MIDI instead of auto-extracting.

For quick local debugging, convert the extracted `*_melody` drafts into approved
short motifs:

```bash
python scripts/music_library/approve_debug_motifs.py --bars 4 --overwrite
```

Validate the library:

```bash
python scripts/music_library/validate_motifs.py
```
