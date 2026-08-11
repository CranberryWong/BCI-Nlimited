from __future__ import annotations

import asyncio
import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

from app.music.recorder import SessionRecorder
from app.music.schemas import MusicEvent

from .audio import AudioLayerEngine, AudioLayerPlan
from .composition import (
    FormEngine,
    HarmonyEngine,
    MelodyGuard,
    MotifEngine,
    OrchestrationEngine,
    PromptCompiler,
    TonalPlanner,
    motif_to_pianoroll,
)
from .config import AdaptiveConfigStore
from .context import ContextHub
from .journal import RuntimeJournal
from .magenta_client import MagentaWorkerClient
from .outputs import OutputHub
from .policy import PolicyEngine
from .schemas import (
    CanonicalMusicEvent,
    ContextFrame,
    FormState,
    HarmonyPlan,
    InputSample,
    MotifPlan,
    MusicIntent,
    OrchestrationPlan,
    TonalPlan,
)
from .sensor_osc import SensorOscServer
from .simulator import AuxiliaryInputSimulator
from .transport import TransportClock


class AdaptivePerformanceRuntime:
    def __init__(
        self,
        configs: AdaptiveConfigStore,
        output: OutputHub,
        recorder: SessionRecorder,
        broadcast,
        notochord_provider=None,
        stems_root: Path | None = None,
        magenta_command: list[str] | None = None,
        magenta_cwd: Path | None = None,
    ) -> None:
        self.configs = configs
        self.output = output
        self.recorder = recorder
        self.broadcast = broadcast
        self.journal = RuntimeJournal(int(configs.get("outputs").get("logging", {}).get("ring_size", 500)))
        self.output.on_error = self._output_log
        self.context_hub = ContextHub(configs.get("inputs"), self._context_log)
        self.policy = PolicyEngine(configs.get("policy"))
        self.tonal_planner = TonalPlanner(configs.get("tonal"))
        self.form_engine = FormEngine(configs.get("form"))
        self.motif_engine = MotifEngine(configs.get("motif"), seed=0)
        self.notochord_provider = notochord_provider
        self.stems_root = stems_root
        self.harmony_engine = HarmonyEngine(configs.get("harmony"), notochord_provider)
        self.orchestration_engine = OrchestrationEngine(configs.get("orchestration"))
        self.audio_layer_engine = AudioLayerEngine(
            configs.get("melody"), configs.get("orchestration"), configs.get("outputs"), stems_root,
        )
        self.prompt_compiler = PromptCompiler(configs.get("melody"))
        self.melody_guard = MelodyGuard(configs.get("melody"))
        form_config = configs.get("form")
        self.transport = TransportClock(84.0, int(form_config.get("beats_per_bar", 4)))
        melody_config = configs.get("melody")
        self.magenta = MagentaWorkerClient(
            str(melody_config.get("worker_url")), self._on_magenta_event, self._model_log,
            command=magenta_command, cwd=magenta_cwd,
        )
        osc_config = configs.get("inputs").get("osc", {})
        self.sensor_osc = SensorOscServer(
            str(osc_config.get("host", "0.0.0.0")),
            int(osc_config.get("port", 8002)),
            self.ingest,
        )
        self.auxiliary_simulator = AuxiliaryInputSimulator(
            self.ingest,
            float(configs.get("inputs").get("simulator", {}).get("interval_seconds", 0.5)),
        )
        self.task: asyncio.Task | None = None
        self.phrase_task: asyncio.Task | None = None
        self.steering_task: asyncio.Task | None = None
        self.dispatch_tasks: set[asyncio.Task] = set()
        self.current_context: ContextFrame | None = None
        self.current_intent: MusicIntent | None = None
        self.current_form: FormState = self.form_engine.state
        self.current_tonal: TonalPlan | None = None
        self.current_motif: MotifPlan | None = None
        self.current_harmony: HarmonyPlan | None = None
        self.current_orchestration: OrchestrationPlan | None = None
        self.current_prompt = ""
        self.current_audio_layer: AudioLayerPlan | None = None
        self.session_id = ""
        self.owns_recording = False
        self.fallback_count = 0
        self.started_at: float | None = None
        self.input_sequence = 0
        self.intent_history: deque[MusicIntent] = deque(maxlen=2400)
        self.scheduler_latencies: deque[float] = deque(maxlen=2000)
        self.transcription_latencies: deque[float] = deque(maxlen=2000)

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    async def startup(self) -> None:
        await self.context_hub.start()
        if self.configs.get("inputs").get("osc", {}).get("enabled", True):
            try:
                await self.sensor_osc.start()
            except OSError as exc:
                self.sensor_osc.detail = f"unavailable: {exc}"
                self._log("warning", "input", "sensor OSC unavailable", {"error": str(exc)})
        if self.output.midi.status.mode != "rtmidi":
            self._log("warning", "output", "MIDI output is in safe mock mode", {
                "detail": self.output.midi.status.detail,
            })
        self._log("info", "system", "adaptive runtime ready", {})

    async def shutdown(self) -> None:
        await self.stop()
        await self.auxiliary_simulator.stop()
        await self.sensor_osc.stop()
        await self.context_hub.stop()

    def ingest(self, sample: InputSample) -> bool:
        accepted = self.context_hub.ingest(sample)
        if accepted:
            self._log("debug", "input", "input sample accepted", {
                "source_id": sample.source_id, "kind": sample.kind, "quality": sample.quality,
            })
        return accepted

    def ingest_bci(self, valence: float, arousal: float, confidence: float, source: str = "bci.primary") -> bool:
        self.input_sequence += 1
        return self.ingest(InputSample(
            source_id=self.configs.get("inputs").get("bci", {}).get("source_id", source),
            kind="bci",
            sequence=self.input_sequence,
            quality=max(0.0, min(1.0, confidence)),
            values={
                "valence": self._normalize_bci_axis(valence),
                "arousal": self._normalize_bci_axis(arousal),
                "confidence": max(0.0, min(1.0, confidence)),
                "original_source": source,
            },
        ))

    async def start(self) -> dict[str, Any]:
        if self.running:
            return self.status()
        snapshot = self.configs.lock()
        self._reconfigure(snapshot)
        self.output.reset_metrics()
        if self.recorder.active_id:
            self.session_id = self.recorder.active_id
            self.owns_recording = False
        else:
            self.session_id = self.recorder.start({"adaptive": snapshot})
            self.owns_recording = True
        self.journal.start(self.session_id, self.recorder.active_dir)
        if self.output.midi.status.mode != "rtmidi":
            self._log("warning", "output", "MIDI output is in safe mock mode", {
                "detail": self.output.midi.status.detail,
            })
        self.recorder.model_metadata = {
            **self.recorder.model_metadata,
            "adaptive": {
                "provider": "magenta_rt2",
                "model": snapshot["melody"].get("model", "mrt2_small"),
                "worker_url": snapshot["melody"].get("worker_url"),
                "frame_hz": snapshot["melody"].get("frame_hz", 25),
                "notochord_enabled": snapshot["harmony"].get("notochord", {}).get("enabled", False),
            },
        }
        self.form_engine.reset()
        self.current_form = self.form_engine.state
        self.fallback_count = 0
        self.started_at = time.time()
        initial_context = self.context_hub.frame()
        initial_intent = self.policy.resolve(initial_context)
        self.current_context = initial_context
        self.current_intent = initial_intent
        self.intent_history.clear()
        self.intent_history.append(initial_intent)
        self.scheduler_latencies.clear()
        self.transcription_latencies.clear()
        bpm = round(58 + initial_intent.energy * 62)
        self.transport.start(bpm)
        await self._plan_phrase(section_changed=True)
        melody_config = self.configs.get("melody")
        audio_layer = self.current_audio_layer
        await self.magenta.start(
            self.current_prompt,
            bool(audio_layer.enabled if audio_layer else melody_config.get("audio", {}).get("enabled", True)),
            float(audio_layer.model_gain if audio_layer else melody_config.get("audio", {}).get("gain", 0.2)),
            audio_layer.output_device if audio_layer else None,
            self.recorder.active_dir,
        )
        self.task = asyncio.create_task(self._run(), name="adaptive-performance")
        self.phrase_task = asyncio.create_task(self._phrase_loop(), name="adaptive-phrase-loop")
        self.steering_task = asyncio.create_task(self._steering_loop(), name="adaptive-magenta-steering")
        self._log("info", "system", "performance started", {"session_id": self.session_id, "bpm": bpm})
        await self._publish("performance_started")
        return self.status()

    async def stop(self) -> dict[str, Any]:
        for task in (self.task, self.phrase_task, self.steering_task):
            if task and task is not asyncio.current_task():
                task.cancel()
        await asyncio.gather(*(task for task in (self.task, self.phrase_task, self.steering_task) if task), return_exceptions=True)
        self.task = self.phrase_task = self.steering_task = None
        for task in tuple(self.dispatch_tasks):
            task.cancel()
        await asyncio.gather(*self.dispatch_tasks, return_exceptions=True)
        self.dispatch_tasks.clear()
        await self.magenta.stop()
        self.output.all_notes_off()
        self.transport.stop()
        if self.started_at is not None:
            self._log("info", "system", "performance stopped", {"session_id": self.session_id})
            self._write_summary()
        if self.owns_recording and self.recorder.active_id:
            self.recorder.stop()
        self.owns_recording = False
        self.started_at = None
        self.configs.unlock()
        self.journal.stop()
        self.session_id = ""
        return self.status()

    def status(self) -> dict[str, Any]:
        position = self.transport.position()
        return {
            "running": self.running,
            "session_id": self.session_id or None,
            "config_locked": self.configs.locked,
            "started_at": self.started_at,
            "transport": {
                "running": self.transport.running,
                "bpm": self.transport.bpm,
                "bar": position.bar,
                "beat": position.beat,
                "phase": position.phase,
            },
            "context": self.current_context.model_dump() if self.current_context else None,
            "intent": self.current_intent.model_dump() if self.current_intent else None,
            "form": self.current_form.model_dump(),
            "tonal": self.current_tonal.model_dump() if self.current_tonal else None,
            "motif": self.current_motif.model_dump() if self.current_motif else None,
            "harmony": self.current_harmony.model_dump() if self.current_harmony else None,
            "orchestration": self.current_orchestration.model_dump() if self.current_orchestration else None,
            "prompt": self.current_prompt,
            "audio_layer": self.current_audio_layer.model_dump() if self.current_audio_layer else None,
            "magenta": self.magenta.status(),
            "fallback_count": self.fallback_count,
            "outputs": self.output.status(),
            "inputs": self.context_hub.public_status(),
            "sensor_osc": {"running": self.sensor_osc.running, "host": self.sensor_osc.host, "port": self.sensor_osc.port, "detail": self.sensor_osc.detail},
            "auxiliary_simulator": {"running": self.auxiliary_simulator.running},
            "recent_logs": self.journal.recent(100),
            "legacy_migration": getattr(self, "legacy_migration", []),
            "windows": {
                "slow_seconds": float(self.configs.get("form").get("slow_window_seconds", 16)),
                "fast_seconds": float(self.configs.get("form").get("fast_window_seconds", 4)),
                "samples": len(self.intent_history),
            },
            "performance_metrics": {
                "scheduler_jitter_p95_ms": self._percentile(self.scheduler_latencies, 0.95),
                "transcription_to_midi_p95_ms": self._percentile(self.transcription_latencies, 0.95),
            },
        }

    async def diagnostics(self) -> dict[str, Any]:
        results = [
            {"name": "config", "ok": all(bool(self.configs.get(name)) for name in self.configs.all())},
            {"name": "midi", "ok": self.output.midi.status.mode == "rtmidi", "detail": self.output.midi.status.detail},
            {"name": "osc", "ok": bool(self.output.osc_clients), "detail": list(self.output.osc_clients)},
            {"name": "magenta", "ok": self.magenta.connected, "detail": self.magenta.status_detail},
            {"name": "bci", "ok": bool(self.current_context and not self.current_context.degraded)},
        ]
        for result in results:
            self._log("info" if result["ok"] else "warning", "test", f"diagnostic: {result['name']}", result)
        await self._publish("diagnostics_completed", {"results": results})
        return {"ok": all(item["ok"] for item in results if item["name"] not in {"magenta", "bci"}), "results": results}

    async def _run(self) -> None:
        tick = 1.0 / max(10.0, float(self.configs.get("outputs").get("osc", {}).get("state_hz", 30)))
        policy_every = max(1, round((1.0 / tick) / max(1.0, float(self.configs.get("policy").get("update_hz", 10)))))
        count = 0
        try:
            while True:
                position = self.transport.position()
                if count % policy_every == 0:
                    self.current_context = self.context_hub.frame()
                    self.current_intent = self.policy.resolve(self.current_context)
                    self.intent_history.append(self.current_intent)
                    self.output.send_state(self.journal.sequence, self.current_context, self.current_intent)
                self.output.send_transport(self.journal.sequence, self.transport.bpm, position.bar, position.beat, position.phase, self.current_form.section_id)
                if count % max(1, round(1.0 / tick)) == 0:
                    self.output.send_health(self.journal.sequence, True, self.magenta.status_detail, self.fallback_count)
                    await self._publish("runtime_tick")
                count += 1
                await asyncio.sleep(tick)
        except asyncio.CancelledError:
            pass

    async def _phrase_loop(self) -> None:
        try:
            while True:
                phrase_seconds = self._phrase_beats * self.transport.seconds_per_beat
                self._schedule_current_phrase()
                await asyncio.sleep(phrase_seconds)
                if self.current_intent is None:
                    continue
                self.current_form, changed = self.form_engine.advance_phrase(self._windowed_form_intent())
                await self._plan_phrase(section_changed=changed)
        except asyncio.CancelledError:
            pass

    async def _steering_loop(self) -> None:
        frame_seconds = 1.0 / max(1.0, float(self.configs.get("melody").get("frame_hz", 25)))
        last_prompt = ""
        try:
            while True:
                if self.current_motif:
                    beat = self.transport.position().absolute_beat
                    prompt = self.current_prompt if self.current_prompt != last_prompt else None
                    await self.magenta.update_conditioning(
                        motif_to_pianoroll(self.current_motif, beat),
                        prompt,
                        audio_gain=self.current_audio_layer.model_gain if prompt and self.current_audio_layer else None,
                        stem_path=self.current_audio_layer.stem_path if prompt and self.current_audio_layer else None,
                        stem_gain=self.current_audio_layer.stem_gain if prompt and self.current_audio_layer else None,
                        stem_crossfade_seconds=self.current_audio_layer.crossfade_seconds if prompt and self.current_audio_layer else None,
                    )
                    last_prompt = self.current_prompt
                await asyncio.sleep(frame_seconds)
        except asyncio.CancelledError:
            pass

    async def _plan_phrase(self, section_changed: bool) -> None:
        if self.current_intent is None:
            return
        self.current_tonal = self.tonal_planner.plan(self.current_intent, section_changed=section_changed)
        self.current_motif = self.motif_engine.plan(self.current_intent, self.current_tonal, self.current_form)
        self.current_harmony = await self.harmony_engine.plan(self.current_tonal, self.current_motif, self.current_form)
        self.current_orchestration = self.orchestration_engine.plan(self.current_intent, self.current_form)
        self.current_audio_layer = self.audio_layer_engine.plan(self.current_form, self.current_orchestration)
        self.current_orchestration = self.current_orchestration.model_copy(update={
            "magenta_audio_gain": self.current_audio_layer.model_gain,
            "stem_gain": self.current_audio_layer.stem_gain,
        })
        self.current_prompt = self.prompt_compiler.compile(self.current_intent, self.current_form)
        if section_changed:
            target_bpm = round(58 + self.current_intent.energy * 62)
            step = max(-6, min(6, target_bpm - self.transport.bpm))
            self.transport.set_bpm(self.transport.bpm + step)
        self._log("info", "form", "phrase planned", {
            "form": self.current_form.model_dump(),
            "tonal": self.current_tonal.model_dump(),
            "motif_id": self.current_motif.id,
            "harmony": self.current_harmony.chords,
            "prompt": self.current_prompt,
            "stem": self.current_audio_layer.stem_path,
        })
        self.output.send_harmony(self.journal.sequence, self.current_harmony, self.current_tonal.root_note, self.current_tonal.scale)
        self.output.send_section(self.journal.sequence, self.current_form, section_changed)
        await self._publish("phrase_planned")

    def _schedule_current_phrase(self) -> None:
        if not all((self.current_motif, self.current_harmony, self.current_orchestration)):
            return
        phrase_start = self.transport.position().absolute_beat
        if not self.magenta.connected:
            self.fallback_count += 1
            for note in self.current_motif.notes:
                self._schedule_note("marimba", note.pitch, note.velocity, note.beat, note.duration_beats, phrase_start, "motif_fallback")
        for note in self.current_harmony.counterpoint:
            self._schedule_note("harmony", note.pitch, note.velocity, note.beat, note.duration_beats, phrase_start, "counterpoint")
        for index, pitch in enumerate(self.current_harmony.bass_pitches):
            self._schedule_note("bass", pitch, self.current_orchestration.role_velocity.get("bass", 64), index * self._beats_per_bar, min(2.0, self._beats_per_bar), phrase_start, "harmony_rule")
        if "pad" in self.current_orchestration.enabled_roles:
            pad_density = self.current_orchestration.role_density.get("pad", 0.0)
            for index, root in enumerate(self.current_harmony.roots):
                if ((index + self.current_form.phrase_index) % 10) / 10.0 <= pad_density:
                    for interval in (0, 4, 7):
                        pitch = 48 + ((root + interval) % 12)
                        self._schedule_note(
                            "pad", pitch, self.current_orchestration.role_velocity.get("pad", 48),
                            index * self._beats_per_bar, self._beats_per_bar * 0.9, phrase_start, "harmony_pad",
                        )
        if "fx" in self.current_orchestration.enabled_roles and self.current_intent:
            self._schedule_control(
                "fx", "spatial_width", self.current_intent.spatial_width,
                phrase_start, "orchestration_rule",
            )
        self._schedule_percussion(phrase_start)

    def _schedule_percussion(self, phrase_start: float) -> None:
        assert self.current_orchestration
        roles = self.configs.get("orchestration").get("roles", {})
        total = self._phrase_beats
        patterns = {
            "kick": [0.0, 2.0],
            "snare": [1.0, 3.0],
            "cymbal": [0.0],
        }
        for role, base_pattern in patterns.items():
            density = self.current_orchestration.role_density.get(role, 0.0)
            if density <= 0.05:
                continue
            pitch = int(roles.get(role, {}).get("note", 36))
            velocity = self.current_orchestration.role_velocity.get(role, 70)
            for bar_start in range(0, total, self._beats_per_bar):
                for offset in base_pattern:
                    selector = ((bar_start + int(offset * 4) + self.current_form.phrase_index) % 10) / 10.0
                    if selector <= density:
                        self._schedule_note(role, pitch, velocity, bar_start + offset, 0.12, phrase_start, "orchestration_rule")
            if role == "snare" and self.current_intent and self.current_intent.transition_urgency > 0.62:
                for offset in (total - 1.0, total - 0.5, total - 0.25):
                    self._schedule_note(role, pitch, min(127, velocity + 10), offset, 0.1, phrase_start, "phrase_fill")

    def _schedule_note(self, role: str, pitch: int, velocity: int, beat: float, duration_beats: float, phrase_start: float, source: str) -> None:
        task = asyncio.create_task(self._dispatch_scheduled_note(role, pitch, velocity, beat, duration_beats, phrase_start, source))
        self.dispatch_tasks.add(task)
        task.add_done_callback(self.dispatch_tasks.discard)

    def _schedule_control(self, role: str, control: str, value: float, phrase_start: float, source: str) -> None:
        async def send() -> None:
            delay = max(0.0, (phrase_start - self.transport.position().absolute_beat) * self.transport.seconds_per_beat)
            await asyncio.sleep(delay)
            position = self.transport.position()
            await self._dispatch(CanonicalMusicEvent(
                source=source, role=role, track_id=role, type="control",
                bar=position.bar, beat=position.beat, control=control, value=value,
                channel=int(self.configs.get("outputs").get("midi", {}).get("channels", {}).get(role, 1)),
            ))

        task = asyncio.create_task(send())
        self.dispatch_tasks.add(task)
        task.add_done_callback(self.dispatch_tasks.discard)

    async def _dispatch_scheduled_note(self, role: str, pitch: int, velocity: int, beat: float, duration_beats: float, phrase_start: float, source: str) -> None:
        target_beat = phrase_start + beat
        delay = max(0.0, (target_beat - self.transport.position().absolute_beat) * self.transport.seconds_per_beat)
        await asyncio.sleep(delay)
        position = self.transport.position()
        scheduler_latency_ms = max(0.0, (position.absolute_beat - target_beat) * self.transport.seconds_per_beat * 1000.0)
        duration_ms = round(duration_beats * self.transport.seconds_per_beat * 1000)
        channel = int(self.configs.get("outputs").get("midi", {}).get("channels", {}).get(role, 1))
        await self._dispatch(CanonicalMusicEvent(
            source=source, role=role, track_id=role, type="note_on", bar=position.bar, beat=position.beat,
            pitch=pitch, velocity=velocity, duration_ms=duration_ms, channel=channel,
            latency_ms=scheduler_latency_ms, metadata={"latency_kind": "scheduler"},
        ))
        await asyncio.sleep(max(0.02, duration_ms / 1000.0))
        position = self.transport.position()
        await self._dispatch(CanonicalMusicEvent(
            source=source, role=role, track_id=role, type="note_off", bar=position.bar, beat=position.beat,
            pitch=pitch, velocity=0, duration_ms=0, channel=channel,
        ))

    async def _on_magenta_event(self, message: dict[str, Any]) -> None:
        if not self.running or self.current_tonal is None:
            return
        position = self.transport.position()
        kind = str(message.get("kind", "note_on"))
        event = CanonicalMusicEvent(
            timestamp=time.time(),
            source="magenta_rt2",
            role="marimba",
            track_id="marimba",
            type=kind if kind in {"note_on", "note_off"} else "note_on",
            bar=position.bar,
            beat=position.beat,
            pitch=int(message.get("note", 60)),
            velocity=int(message.get("velocity", 80)),
            duration_ms=int(message.get("duration_ms", 80)),
            channel=int(self.configs.get("outputs").get("midi", {}).get("channels", {}).get("marimba", 1)),
            latency_ms=max(0.0, (time.time() - float(message.get("generated_at", time.time()))) * 1000.0),
            metadata={"confidence": message.get("confidence", 0.0), "frequency": message.get("frequency")},
        )
        chord_root = None
        if self.current_harmony and self.current_harmony.roots:
            chord_index = int(position.absolute_beat // self._beats_per_bar) % len(self.current_harmony.roots)
            chord_root = self.current_harmony.roots[chord_index]
        guarded = self.melody_guard.apply(event, self.current_tonal, chord_root, self.transport.seconds_per_beat)
        await self._dispatch(guarded)

    async def _dispatch(self, event: CanonicalMusicEvent) -> None:
        if event.metadata.get("latency_kind") == "scheduler":
            self.scheduler_latencies.append(event.latency_ms)
        elif event.source == "magenta_rt2":
            self.transcription_latencies.append(event.latency_ms)
        resolved = self.journal.record_event(event)
        self.output.dispatch(resolved)
        legacy_type = resolved.type if resolved.type in {"note_on", "note_off", "control", "osc"} else "control"
        legacy = MusicEvent(
            timestamp=resolved.timestamp,
            track_id=resolved.track_id,
            type=legacy_type,
            pitch=resolved.pitch,
            velocity=resolved.velocity,
            duration_ms=resolved.duration_ms,
            channel=resolved.channel,
            args=[resolved.control, resolved.value] if resolved.control else [],
        )
        self.recorder.record_event(legacy)
        await self.broadcast({
            "version": "v1",
            "type": "music_event",
            "seq": resolved.sequence,
            "timestamp": resolved.timestamp,
            "session_id": self.session_id,
            "payload": {"event": resolved.model_dump(), "status": self.status()},
        })

    async def _publish(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        await self.broadcast({
            "version": "v1",
            "type": kind,
            "seq": self.journal.sequence,
            "timestamp": time.time(),
            "session_id": self.session_id,
            "payload": {**(payload or {}), "status": self.status()},
        })

    def _reconfigure(self, snapshot: dict[str, Any]) -> None:
        self.context_hub.config = snapshot["inputs"]
        self.policy = PolicyEngine(snapshot["policy"])
        self.tonal_planner = TonalPlanner(snapshot["tonal"])
        self.form_engine = FormEngine(snapshot["form"])
        self.motif_engine = MotifEngine(snapshot["motif"], seed=0)
        self.harmony_engine = HarmonyEngine(snapshot["harmony"], self.notochord_provider)
        self.orchestration_engine = OrchestrationEngine(snapshot["orchestration"])
        self.audio_layer_engine = AudioLayerEngine(
            snapshot["melody"], snapshot["orchestration"], snapshot["outputs"], self.stems_root,
        )
        self.prompt_compiler = PromptCompiler(snapshot["melody"])
        self.melody_guard = MelodyGuard(snapshot["melody"])
        self.output.update_config(snapshot["outputs"])

    def _windowed_form_intent(self) -> MusicIntent:
        assert self.current_intent is not None
        now = self.current_intent.timestamp
        form = self.configs.get("form")
        slow_seconds = float(form.get("slow_window_seconds", 16))
        fast_seconds = float(form.get("fast_window_seconds", 4))
        while self.intent_history and now - self.intent_history[0].timestamp > slow_seconds * 2:
            self.intent_history.popleft()
        slow = [item for item in self.intent_history if now - item.timestamp <= slow_seconds]
        fast = [item for item in self.intent_history if now - item.timestamp <= fast_seconds]
        if not slow or not fast:
            return self.current_intent

        def average(items: list[MusicIntent], field: str) -> float:
            return sum(float(getattr(item, field)) for item in items) / len(items)

        values = self.current_intent.model_dump()
        for field in ("valence", "energy", "tension", "density", "brightness", "pulse", "complexity", "spatial_width"):
            values[field] = average(slow, field)
        emotion_delta = abs(average(fast, "valence") - average(slow, "valence"))
        energy_delta = abs(average(fast, "energy") - average(slow, "energy"))
        values["transition_urgency"] = max(
            average(slow, "transition_urgency"),
            min(1.0, emotion_delta * 1.5 + energy_delta),
        )
        values["confidence"] = average(slow, "confidence")
        values["frozen_motif"] = any(item.frozen_motif for item in fast)
        return MusicIntent.model_validate(values)

    def _write_summary(self) -> None:
        if self.recorder.active_dir is None:
            return
        payload = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "stopped_at": time.time(),
            "duration_seconds": max(0.0, time.time() - self.started_at) if self.started_at else 0.0,
            "form": self.current_form.model_dump(),
            "fallback_count": self.fallback_count,
            "magenta": self.magenta.status(),
            "outputs": self.output.status(),
            "performance_metrics": {
                "scheduler_jitter_p95_ms": self._percentile(self.scheduler_latencies, 0.95),
                "transcription_to_midi_p95_ms": self._percentile(self.transcription_latencies, 0.95),
            },
            "log_entries": len(self.journal.entries),
            "canonical_events": len(self.journal.events),
        }
        try:
            (self.recorder.active_dir / "adaptive_summary.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
            )
        except OSError as exc:
            self._log("error", "system", "could not write session summary", {"error": str(exc)})

    @property
    def _beats_per_bar(self) -> int:
        return int(self.configs.get("form").get("beats_per_bar", 4))

    @property
    def _phrase_beats(self) -> int:
        return int(self.configs.get("form").get("phrase_bars", 2)) * self._beats_per_bar

    def _log(self, level: str, category: str, message: str, data: dict[str, Any]) -> None:
        self.journal.log(level, category, message, data)

    def _context_log(self, level: str, message: str, data: dict[str, Any]) -> None:
        self._log(level, "input", message, data)

    def _model_log(self, level: str, message: str, data: dict[str, Any]) -> None:
        self._log(level, "model", message, data)

    def _output_log(self, level: str, message: str, data: dict[str, Any]) -> None:
        self._log(level, "output", message, data)

    @staticmethod
    def _normalize_bci_axis(value: float) -> float:
        value = float(value)
        return max(0.0, min(1.0, (value - 1.0) / 8.0)) if value > 1.0 else max(0.0, min(1.0, value))

    @staticmethod
    def _percentile(values: deque[float], quantile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * quantile) - 1))
        return round(float(ordered[index]), 3)
