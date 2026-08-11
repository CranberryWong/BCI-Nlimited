# BCI Music Dashboard

BCI Music Dashboard is a FastAPI and Vue 3 single page dashboard for turning realtime
`[valence, arousal, prob0, prob1]` tuples into emotion telemetry, generated music
events, OSC/MIDI output, and reproducible session exports.

The primary runtime is now `adaptive_performance`: BCI remains the emotional source
of truth while time, weather, heart rate, motion, light, and posture provide bounded
auxiliary modulation. A YAML policy compiles those inputs into `MusicIntent`, then
independent tonal, form, motif, harmony, counterpoint, melody, and orchestration
modules feed one transport clock and one central output hub. Legacy generators and
routes remain available for one migration cycle, but are not dependencies of the new
runtime.

## Project Layout

- `backend/app/bci`: OSC input, async simulator, XDF/model watcher, emotion mapping.
- `backend/app/music`: YAML-backed config, track schemas, music engine, MIDI/OSC output, recording.
- `backend/app/adaptive`: input contracts, Context Hub, policy, composition planners,
  MRT2 client, Transport, OutputHub, unified journal, and performance runtime.
- `backend/app/config/{inputs,policy,form,tonal,motif,melody,harmony,orchestration,outputs}.yaml`:
  the complete adaptive performance configuration.
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

5. Open `Adaptive Config`, set the explicit weather latitude/longitude if weather is
   enabled, then click `Start Performance`. Configuration is immutable until the
   performance stops.

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

## Docker Compose (rule fallback)

Docker is a compatibility/development mode. The formal MRT2 performance environment
is an Apple Silicon Mac running native processes. In Docker or Windows, the frontend
is built once and served by Nginx, which proxies `/api` and `/ws` to FastAPI. Models,
presets, sessions, and XDF recordings stay on host-mounted directories, while melody
generation uses the deterministic motif-rule fallback.

### Online target workstation

```bash
cd bci-music-dashboard
cp .env.example .env
docker compose up --build
```

On Windows PowerShell:

```powershell
cd bci-music-dashboard
.\scripts\start-docker.ps1
```

Set the Windows XDF directory in `.env`, for example:

```env
HOST_XDF_ROOT_DIR=C:/Users/SJTU/.leaf/record
```

The stack exposes the dashboard on `5173`, API on `8001`, and UDP OSC input on
`8000`.

### Offline target workstation

Build a transferable Linux/AMD64 bundle on the development machine:

```bash
./scripts/export-docker-bundle.sh linux/amd64
```

Copy the generated `docker-bundle/` directory to the Windows workstation. With Docker
Desktop running in Linux container mode:

```powershell
cd D:\path\to\docker-bundle
Set-ExecutionPolicy -Scope Process Bypass
.\start-windows.ps1
```

The bundle contains both Docker images, Compose configuration, the model when
available, current preset/session data, and a Windows loader. The target machine does
not need Python, Node.js, npm, or access to a container registry.

Direct host MIDI access from Docker Desktop is unreliable. For container deployment,
send OSC to the host and convert it to MIDI in Max/MSP or a small host-side bridge.
The Compose environment maps default localhost OSC output to `host.docker.internal`.

## Input Modes

- Real model: set `XDF_ROOT_DIR`, place the model file, then call
  `POST /api/control/start-model` or click `Start Model`.
- Simulator: call `POST /api/control/start-simulator` or click `Start Simulator`.
  It reuses the old test payload shape without a blocking main-thread loop.
- OSC input: send `/eeg/valence_arousal` with four args to
  `BCI_INPUT_OSC_IP:BCI_INPUT_OSC_PORT`, default UDP port `8000`.

BCI OSC port `8000` is distinct from generic sensor OSC port `8002`. Sensor adapters
accept normalized heart rate, motion, light, and posture messages; Kinect or any
future body tracker only needs to publish `motion`, `expansion`, `symmetry`,
`verticality`, `gesture`, and `confidence` rather than linking its SDK to the music
core.

Weather uses Open-Meteo outside the realtime loop with a 1.5 second timeout, ten
minute refresh, three-failure circuit breaker, and a thirty-minute last-valid cache.
An unavailable service never blocks Transport.

## Adaptive Performance API

- `GET /api/inputs/status`
- `POST /api/inputs/{source_id}/sample`
- `GET|PUT /api/config/{module}`
- `POST /api/performance/start|stop`
- `GET /api/runtime/status`
- `POST /api/diagnostics/run`

Realtime WebSocket messages use the versioned envelope
`{version,type,seq,timestamp,session_id,payload}`. YAML is the human-authored source;
JSON is used only for HTTP, WebSocket, OSC metadata, and logs.

Run the two-hour onsite acceptance monitor against a live native backend with:

```bash
python backend/scripts/soak_adaptive.py --duration-seconds 7200
```

It always stops the performance in `finally` and fails on MRT2 frame time,
transcription-to-MIDI p95, scheduler jitter, or an unexpected runtime stop.

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

Each non-percussion track exposes two independent density controls:

- `Onset Density` controls how frequently note events are triggered over time.
- `Polyphony` controls how many notes sound at each trigger. Melody voices follow the
  active scale, chord/pad voices extend the chord, and bass voices favor fifths and octaves.

Both values are included when saving a preset.

## Central Outputs

The adaptive runtime has no per-track IP or port. `outputs.yaml` owns the MIDI device,
role-to-channel map, audio settings, and all OSC targets. TouchDesigner defaults to
`127.0.0.1:9000` and receives:

```text
/v1/music/note
/v1/music/transport
/v1/music/state
/v1/music/harmony
/v1/music/section
/v1/music/health
```

TouchDesigner and physical instruments are dispatched in parallel; visual latency or
failure cannot hold the music clock. Legacy per-track targets are imported as disabled
central targets for operator review.

MIDI output uses `mido` and tries `python-rtmidi`. If host MIDI support is absent,
`GET /api/outputs/midi-ports` reports mock mode instead of crashing.

## Sessions And Reproducibility

Recording APIs:

- `POST /api/sessions/start`
- `POST /api/sessions/stop`
- `GET /api/sessions`
- `GET /api/sessions/{id}/download?format=mid|wav|csv|emotion-jsonl|music-jsonl|runtime-log|summary|config`

Each stopped session stores:

- emotion time series CSV;
- emotion timeline JSONL;
- music event log JSONL;
- canonical adaptive runtime event/log JSONL;
- generated MIDI file;
- `music_config_snapshot.yaml`.

Those artifacts preserve the input emotion stream, event decisions, exported MIDI,
and the exact music configuration used for an experiment.

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

`MIRROR` and `ENGAGING` remain only on legacy routes during the migration period.
They are not exposed by `adaptive_performance`, which has one pre-performance policy
snapshot and no user mode switch.
