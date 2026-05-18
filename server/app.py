from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from server.config import AppConfig, load_config
from server.outputs.midi import MidiOutput
from server.outputs.osc import OscOutput
from server.pipeline.xdf import RealStreamWatcher
from server.state import StateStore
from server.testing.fake_stream import FakeStreamRunner


class BciServer:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.state = StateStore()
        self.osc = OscOutput(self.config)
        self.midi = MidiOutput(self.config)
        self.real_watcher: RealStreamWatcher | None = None
        self.fake_stream = FakeStreamRunner(self.handle_sample)
        self.state.patch(
            osc_ready=self.osc.ready,
            osc_error=self.osc.error,
            midi_ready=self.midi.ready,
            midi_error=self.midi.error,
        )

    def handle_sample(
        self,
        valence: int,
        arousal: int,
        prob0: float | None,
        prob1: float | None,
        source: str,
    ) -> None:
        sample = self.state.update_sample(valence, arousal, prob0, prob1, source)
        try:
            payload = self.osc.send(sample.valence, sample.arousal, sample.prob0, sample.prob1)
            self.state.patch(osc_ready=True, osc_error=None, last_log=f"OSC sent: {payload}")
        except Exception as exc:
            self.state.patch(osc_ready=False, osc_error=str(exc))
            self.state.error(f"OSC send failed: {exc}")
        messages = self.midi.send(sample.valence, sample.arousal, sample.confidence)
        self.state.patch(
            midi_ready=self.midi.ready,
            midi_error=self.midi.error,
            last_log=f"MIDI sent: {messages}" if messages else self.state.snapshot().get("last_log"),
        )

    def apply_config(self, values: dict[str, Any]) -> dict[str, Any]:
        was_test_running = self.fake_stream.running
        was_real_running = self.real_watcher.running if self.real_watcher else False
        if was_test_running:
            self.stop_test_stream()
        if was_real_running:
            self.stop_real_stream()
        self.config.update(values)
        self.osc.configure(self.config)
        self.midi.configure(self.config)
        self.state.patch(
            osc_ready=self.osc.ready,
            osc_error=self.osc.error,
            midi_ready=self.midi.ready,
            midi_error=self.midi.error,
        )
        if was_real_running:
            self.start_real_stream()
        if was_test_running:
            self.start_test_stream()
        return self.config.to_dict()

    def start_real_stream(self) -> None:
        self.stop_test_stream()
        self.real_watcher = RealStreamWatcher(self.config, self.state, self.handle_sample)
        self.real_watcher.start()

    def stop_real_stream(self) -> None:
        if self.real_watcher is not None:
            self.real_watcher.stop()
            self.real_watcher = None

    def start_test_stream(self) -> None:
        self.stop_real_stream()
        self.fake_stream.start()
        self.state.patch(
            running=True,
            mode="test",
            test_stream_running=True,
            finished=False,
        )

    def stop_test_stream(self) -> None:
        self.fake_stream.stop()
        self.state.patch(test_stream_running=False)

    def stop_all(self) -> None:
        self.stop_test_stream()
        self.stop_real_stream()
        self.state.patch(running=False, mode="idle", finished=True)


def create_app(config: AppConfig | None = None) -> Flask:
    service = BciServer(config)
    static_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="")
    app.config["BCI_SERVICE"] = service

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,OPTIONS"
        return response

    @app.route("/api/status")
    def status():
        return jsonify(
            {
                "state": service.state.snapshot(),
                "config": service.config.to_dict(),
                "midi_ports": MidiOutput.available_ports() if service.config.midi_enabled else [],
            }
        )

    @app.route("/api/latest")
    def latest():
        return jsonify(service.state.latest())

    @app.route("/api/config", methods=["GET", "PUT", "OPTIONS"])
    def config_route():
        if request.method == "OPTIONS":
            return ("", 204)
        if request.method == "GET":
            return jsonify(service.config.to_dict())
        values = request.get_json(silent=True) or {}
        return jsonify(service.apply_config(values))

    @app.route("/api/start", methods=["POST", "OPTIONS"])
    def start():
        if request.method == "OPTIONS":
            return ("", 204)
        payload = request.get_json(silent=True) or {}
        mode = payload.get("mode", "xdf")
        if mode == "test":
            service.start_test_stream()
        else:
            service.start_real_stream()
        return jsonify(service.state.snapshot())

    @app.route("/api/stop", methods=["POST", "OPTIONS"])
    def stop():
        if request.method == "OPTIONS":
            return ("", 204)
        service.stop_all()
        return jsonify(service.state.snapshot())

    @app.route("/api/test-stream/start", methods=["POST", "OPTIONS"])
    def test_stream_start():
        if request.method == "OPTIONS":
            return ("", 204)
        service.start_test_stream()
        return jsonify(service.state.snapshot())

    @app.route("/api/test-stream/stop", methods=["POST", "OPTIONS"])
    def test_stream_stop():
        if request.method == "OPTIONS":
            return ("", 204)
        service.stop_test_stream()
        service.state.patch(running=False, mode="idle", finished=True)
        return jsonify(service.state.snapshot())

    @app.route("/api/events")
    def events():
        def stream():
            while True:
                yield f"data: {json.dumps(service.state.snapshot())}\n\n"
                time.sleep(1.0)

        return Response(stream(), mimetype="text/event-stream")

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path: str):
        if static_dir.exists():
            target = static_dir / path
            if path and target.exists():
                return send_from_directory(static_dir, path)
            return send_from_directory(static_dir, "index.html")
        return jsonify(
            {
                "message": "BCI server is running. Start the Vue dev server in frontend/ for the UI.",
                "api": "/api/status",
            }
        )

    return app


def main() -> None:
    config = load_config()
    app = create_app(config)
    app.run(host=config.host, port=config.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
