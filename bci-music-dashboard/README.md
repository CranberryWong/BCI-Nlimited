# BCI Music Dashboard

BCI Music Dashboard is a FastAPI and Vue 3 single page dashboard for turning realtime
`[valence, arousal, prob0, prob1]` tuples into emotion telemetry, generated music
events, OSC/MIDI output, and reproducible session exports.

## Project Layout

- `backend/app/bci`: OSC input, async simulator, XDF/model watcher, emotion mapping.
- `backend/app/music`: YAML-backed config, track schemas, music engine, MIDI/OSC output, recording.
- `frontend/src/views/Dashboard`: monitor, track editor, output test, recorder, music config drawer.
- `models`: local model drop folder. The directory is tracked; `.pkl` files are ignored.
- `backend/app/legacy`: untouched copies of the old Flask OSC sender and test sender.

## Model Placement

Please place the emotion model at:

```text
models/mlp_valence_model.pkl
```

The backend resolves the default relative model path from the project root. Override it
with `MODEL_PATH=models/mlp_valence_model.pkl` or an absolute path. A missing model is
reported as `model_missing`; the backend and simulator still start, while
`POST /api/control/start-model` returns a clear error.

## Local Development

1. Create the environment file:

   ```bash
   cd bci-music-dashboard
   cp .env.example .env
   ```

2. Start the backend:

   ```bash
   cd backend
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
   ```

   FastAPI docs are at `http://127.0.0.1:8001/docs`.

3. Start the frontend:

   ```bash
   cd ../frontend
   npm install
   npm run dev
   ```

   Open `http://127.0.0.1:5173`.

4. Click `Start Simulator`. The dashboard curve and music event table update through
   `/ws/realtime`.

## Windows

Use PowerShell from `bci-music-dashboard`:

```powershell
Copy-Item .env.example .env
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

In a second PowerShell window run `npm install` and `npm run dev` in `frontend`.
Set `XDF_ROOT_DIR` in `.env` to the Leaf recording root when using real XDF input.

## macOS

The local development commands above work on macOS. For virtual MIDI routing, create
an IAC bus in Audio MIDI Setup, refresh `GET /api/outputs/midi-ports`, set a track to
`midi`, and choose an output mode that includes MIDI. If no port is available,
the backend remains in mock MIDI mode.

## Docker Compose

```bash
cd bci-music-dashboard
cp .env.example .env
docker compose up --build
```

The compose stack exposes frontend `5173`, backend `8001`, and UDP input OSC port
`8000`. The `models` directory is mounted read-only and `backend/data` persists
presets and sessions.

## Input Modes

- Real model: set `XDF_ROOT_DIR`, place the model file, then call
  `POST /api/control/start-model` or click `Start Model`.
- Simulator: call `POST /api/control/start-simulator` or click `Start Simulator`.
  It reuses the old test payload shape without a blocking main-thread loop.
- OSC input: send `/eeg/valence_arousal` with four args to
  `BCI_INPUT_OSC_IP:BCI_INPUT_OSC_PORT`, default UDP port `8000`.

Input OSC port `8000` is distinct from output OSC targets. Output OSC defaults to
`127.0.0.1:57120` for Max/MSP but each track can override IP and port.

## Music Configuration

Default music parameters live in:

```text
backend/app/config/music_defaults.yaml
```

That YAML holds global settings, emotion profiles, default tracks, editable ranges,
scales and output mode defaults. Runtime priority is:

1. Dashboard edits applied through `PUT /api/music/config` or track patches.
2. The loaded preset snapshot.
3. `music_defaults.yaml`.
4. Small code safety fallbacks.

Open `Music Config` in the dashboard to edit global BPM/root/scale/quantization,
emotion profiles, and track-level mappings. `Apply` changes the active engine without
restarting the backend. `Save Preset` snapshots the current config into
`backend/data/presets`. Config snapshots can be exported as YAML and imported from
YAML or JSON.

## Outputs

OSC note events use addresses such as:

```text
/music/track/{track_id}/note
/music/track/{track_id}/control
/music/emotion
/music/global
```

For Max/MSP, listen on the track target port, commonly `57120`, and parse the note
payload `[event_type, pitch, velocity, duration_ms, midi_channel]`. Use the dashboard
`Test Output` button or `POST /api/outputs/test` to send a test note.

MIDI output uses `mido` and tries `python-rtmidi`. If host MIDI support is absent,
`GET /api/outputs/midi-ports` reports mock mode instead of crashing.

## Sessions And Reproducibility

Recording APIs:

- `POST /api/sessions/start`
- `POST /api/sessions/stop`
- `GET /api/sessions`
- `GET /api/sessions/{id}/download?format=mid|jsonl|csv`

Each stopped session stores:

- emotion time series CSV;
- music and OSC-style event timeline JSONL;
- generated MIDI file;
- `music_config_snapshot.yaml`.

Those artifacts preserve the input emotion stream, event decisions, exported MIDI,
OSC timeline, and the exact music configuration used for an experiment.

## Presets And API

Built-in presets include Ambient Neurofeedback, Piano Emotion Melody, Percussive
Arousal, and Max/MSP OSC Bridge. Presets are config snapshots rather than a separate
parameter system.

Config APIs:

- `GET /api/music/config`
- `PUT /api/music/config`
- `POST /api/music/config/reset`
- `GET /api/music/config/export`
- `POST /api/music/config/import`
- `PATCH /api/tracks/{track_id}`
- `POST /api/tracks/{track_id}/reset`

## Legacy Compatibility

The old `app_send_osc.py` and `send_osc_fortest.py` are copied under
`backend/app/legacy`. They are not imported by FastAPI. Their reusable XDF parsing,
model windowing, model probability mapping, OSC tuple layout, and simulator tuple
layout have been moved into the modular backend services.
