from __future__ import annotations

import time
from typing import Any

from pythonosc.udp_client import SimpleUDPClient

from app.music.midi_output import MidiOutput
from app.music.schemas import MusicEvent, TrackConfig

from .schemas import CanonicalMusicEvent, ContextFrame, FormState, HarmonyPlan, MusicIntent


class OutputHub:
    """Central endpoint routing; tracks no longer own network destinations."""

    def __init__(self, config: dict[str, Any], midi: MidiOutput) -> None:
        self.config = config
        self.midi = midi
        self.osc_clients: dict[str, SimpleUDPClient] = {}
        self.events_sent = 0
        self.midi_attempted = 0
        self.midi_sent = 0
        self.osc_sent = 0
        self.errors = 0
        self.last_error = ""
        self.on_error = None
        self.started_at = time.time()
        self.last_error_logged_at = 0.0
        preferred = str(config.get("midi", {}).get("port_contains", ""))
        if preferred:
            self.midi.configure(preferred_port=preferred)
        self._configure_osc()

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.osc_clients = {}
        preferred = str(config.get("midi", {}).get("port_contains", ""))
        self.midi.configure(preferred_port=preferred)
        self._configure_osc()

    def dispatch(self, event: CanonicalMusicEvent) -> None:
        self.events_sent += 1
        if self.config.get("midi", {}).get("enabled", True) and event.type in {"note_on", "note_off", "control"}:
            try:
                track = self._track(event.role, event.track_id)
                legacy = MusicEvent(
                    timestamp=event.timestamp,
                    track_id=event.track_id,
                    type=event.type,
                    pitch=event.pitch,
                    velocity=event.velocity,
                    duration_ms=event.duration_ms,
                    channel=event.channel or track.midi_channel,
                    args=[event.control, event.value] if event.control else [],
                )
                self.midi.send_event(track, legacy)
                self.midi_attempted += 1
                if self.midi.status.mode == "rtmidi":
                    self.midi_sent += 1
            except Exception as exc:
                self._error(exc)
        self._osc("/v1/music/note" if event.type in {"note_on", "note_off"} else "/v1/music/control", [
            event.sequence,
            event.timestamp,
            event.role,
            event.type,
            event.pitch or 0,
            event.velocity or 0,
            event.duration_ms or 0,
            event.channel or self._channel(event.role),
            event.bar,
            event.beat,
        ])

    def send_transport(self, sequence: int, bpm: float, bar: int, beat: float, phase: float, section: str) -> None:
        self._osc("/v1/music/transport", [sequence, time.time(), bpm, bar, beat, phase, section])

    def send_state(self, sequence: int, context: ContextFrame, intent: MusicIntent) -> None:
        self._osc("/v1/music/state", [
            sequence, time.time(), context.valence, context.arousal, intent.energy,
            intent.density, intent.brightness, intent.tension, intent.confidence,
            intent.spatial_width,
        ])

    def send_harmony(self, sequence: int, harmony: HarmonyPlan, root: str, scale: str) -> None:
        self._osc("/v1/music/harmony", [sequence, time.time(), root, scale, harmony.chords[0] if harmony.chords else "", harmony.roots[0] if harmony.roots else 0])

    def send_section(self, sequence: int, form: FormState, changed: bool) -> None:
        self._osc("/v1/music/section", [sequence, time.time(), form.section_id, form.role, form.phrase_index, form.phrase_in_section, int(changed)])

    def send_health(self, sequence: int, running: bool, model_status: str, fallback_count: int) -> None:
        self._osc("/v1/music/health", [sequence, time.time(), int(running), model_status, fallback_count, self.errors])

    def all_notes_off(self) -> None:
        self.midi.all_notes_off()
        self._osc("/v1/music/control", [0, time.time(), "system", "all_notes_off", 0, 0, 0, 0, 0, 0.0])

    def reset_metrics(self) -> None:
        self.events_sent = 0
        self.midi_attempted = 0
        self.midi_sent = 0
        self.osc_sent = 0
        self.errors = 0
        self.last_error = ""
        self.started_at = time.time()
        self.last_error_logged_at = 0.0

    def status(self) -> dict[str, Any]:
        return {
            "events_sent": self.events_sent,
            "midi_sent": self.midi_sent,
            "midi_attempted": self.midi_attempted,
            "osc_sent": self.osc_sent,
            "errors": self.errors,
            "last_error": self.last_error,
            "midi": self.midi.status.__dict__,
            "osc_targets": list(self.osc_clients),
        }

    def _track(self, role: str, track_id: str) -> TrackConfig:
        return TrackConfig(
            id=track_id,
            name=role.replace("_", " ").title(),
            role=self._legacy_role(role),
            instrument=role,
            output_type="midi",
            midi_channel=self._channel(role),
        )

    def _channel(self, role: str) -> int:
        return int(self.config.get("midi", {}).get("channels", {}).get(role, 1))

    @staticmethod
    def _legacy_role(role: str) -> str:
        return {
            "marimba": "melody",
            "harmony": "chord",
            "kick": "drum",
            "snare": "drum",
        }.get(role, role if role in {"melody", "chord", "bass", "drum", "cymbal", "pad", "fx"} else "fx")

    def _configure_osc(self) -> None:
        if not self.config.get("osc", {}).get("enabled", True):
            return
        for target in self.config.get("osc", {}).get("targets", []):
            if target.get("enabled", True):
                self.osc_clients[str(target.get("id", "target"))] = SimpleUDPClient(str(target.get("host", "127.0.0.1")), int(target.get("port", 9000)))

    def _osc(self, address: str, args: list[Any]) -> None:
        for client in self.osc_clients.values():
            try:
                client.send_message(address, args)
                self.osc_sent += 1
            except OSError as exc:
                self._error(exc)

    def _error(self, exc: Exception) -> None:
        self.errors += 1
        self.last_error = str(exc)
        now = time.time()
        if self.on_error and (self.errors == 1 or now - self.last_error_logged_at >= 5.0):
            self.last_error_logged_at = now
            self.on_error("error", "output failure", {"error": str(exc), "count": self.errors})
