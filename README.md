# BCI Dataflow Server

Local BCI data-flow server with a Vue control console, OSC output, MIDI CC
output, a real XDF pipeline, and a built-in test stream.

## Architecture

- `server/app.py` runs the Flask API and serves the built web UI.
- `server/pipeline/` watches XDF session folders and performs EEG inference.
- `server/outputs/osc.py` sends `/eeg/valence_arousal` payloads.
- `server/outputs/midi.py` maps valence, arousal, and confidence to MIDI CC.
- `server/testing/` contains reusable fake OSC sender and validation receiver.
- `frontend/` contains the Vue + Vite control console.

The OSC payload shape is always:

```text
[valence, arousal, prob0, prob1]
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install the web UI dependencies:

```bash
npm install --prefix frontend
```

## Run

Start the Python server:

```bash
python -m server.app
```

Start the Vue development server:

```bash
npm --prefix frontend run dev
```

Open:

```text
http://127.0.0.1:5173
```

The Flask API defaults to `http://127.0.0.1:5000`. The Vue dev server proxies
`/api` requests to Flask.

## Test Stream and OSC Validation

Terminal 1, start the OSC receiver:

```bash
python validation_fortest.py
```

Terminal 2, send fake OSC packets:

```bash
python send_osc_fortest.py
```

The default target is `127.0.0.1:8000` and the default OSC address is
`/eeg/valence_arousal`.

You can also use the Web UI's Test Stream page to generate the same shape of
data through the server, which then sends both OSC and MIDI.

## Configuration

Environment variables can override defaults:

```bash
BCI_PORT=5000
XDF_ROOT_DIR=/path/to/record
MODEL_PATH=/path/to/mlp_valence_model.pkl
OSC_TARGET_IP=127.0.0.1
OSC_TARGET_PORT=8000
OSC_ADDRESS=/eeg/valence_arousal
MIDI_PORT_NAME="IAC Driver Bus 1"
```

The Web UI can update the same runtime configuration while the server is
running.

## MIDI

Default MIDI CC mapping:

- Valence -> CC20
- Arousal -> CC21
- Confidence -> CC22

On macOS, enable IAC Driver in Audio MIDI Setup for a virtual MIDI bus. On
Windows, install a virtual MIDI port such as loopMIDI.

## GitHub Collaboration

- Keep `main` runnable.
- Use feature branches and PRs for UI, MIDI, and pipeline work.
- Do not commit large model files; pass them via `MODEL_PATH`.
- Keep test tools in `server/testing/` and top-level compatibility scripts thin.

