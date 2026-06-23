from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Awaitable, Callable

from app.music.generation.emotion_window import EmotionWindowAggregator
from app.music.generation.form import CompositionStateMachine, FormPosition
from app.music.generation.mode_control import ModeController
from app.music.generation.model import MelodyModel
from app.music.generation.motif_composer import MotifComposer
from app.music.generation.motif_library import Motif, MotifLibrary
from app.music.generation.scoring import CandidateScorer
from app.music.generation.theme_composer import ThemeComposer
from app.music.generation.theme_library import Theme, ThemeLibrary
from app.music.generation.transition import EmotionTransitionPlanner, TransitionPlan
from app.music.schemas import (
    ActiveMusicConfig,
    EmotionState,
    MusicEvent,
    MusicGeneratorConfig,
    MusicSegment,
    SystemMode,
)


Broadcast = Callable[[dict], Awaitable[None]]
RecordSegment = Callable[[MusicSegment], None]
RecordStatus = Callable[[dict], None]


class MusicGenerationRuntime:
    def __init__(
        self,
        config: MusicGeneratorConfig,
        music_config: ActiveMusicConfig,
        model: MelodyModel,
        theme_library: ThemeLibrary,
        motif_library: MotifLibrary,
        dispatch: Callable[[MusicEvent], None],
        all_notes_off: Callable[[], None],
        broadcast: Broadcast,
        record_segment: RecordSegment,
        record_status: RecordStatus,
    ) -> None:
        self.config = config
        self.music_config = music_config
        self.model = model
        self.theme_library = theme_library
        self.motif_library = motif_library
        self.dispatch = dispatch
        self.all_notes_off = all_notes_off
        self.broadcast = broadcast
        self.record_segment = record_segment
        self.record_status = record_status
        self.aggregator = EmotionWindowAggregator(config.window_seconds, config.minimum_samples)
        self.fast_aggregator = EmotionWindowAggregator(config.fast_window_seconds, 1)
        self.mode_controller = ModeController(music_config.system_modes, config.system_mode)
        self.composer = ThemeComposer()
        self.motif_composer = MotifComposer()
        self.scorer = CandidateScorer()
        self.transition_planner = EmotionTransitionPlanner()
        self.form = CompositionStateMachine()
        self.task: asyncio.Task | None = None
        self.status_task: asyncio.Task | None = None
        self.playing_segment: MusicSegment | None = None
        self.next_segment: MusicSegment | None = None
        self.selected_theme_id = config.theme_id
        self.current_theme: Theme | None = None
        self.current_motif: Motif | None = None
        self.current_position: FormPosition | None = None
        self.current_bpm = config.emotion_bpm["neutral"]
        self.current_emotion = "neutral"
        self.candidate_emotion = "neutral"
        self.segment_started_at: float | None = None
        self.experience_started_at: float | None = None
        self.last_generation_ms = 0.0
        self.fallback_count = 0
        self.generation_error = ""
        self.dispatch_tasks: set[asyncio.Task] = set()
        self.last_published_stage: str | None = None
        self.last_segment_source = "theme"
        self.last_transition: TransitionPlan | None = None
        self.motif_phrase_count = 0

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def add_emotion(self, emotion: EmotionState) -> None:
        self.aggregator.add(emotion)
        self.fast_aggregator.add(emotion)
        self.mode_controller.update_emotion(emotion)
        if self.running:
            self._dispatch_expression(emotion)

    def update_music_config(self, music_config: ActiveMusicConfig) -> None:
        self.music_config = music_config
        self.mode_controller.configure(music_config.system_modes)

    def update_settings(self, payload: dict[str, Any]) -> dict:
        allowed = {"theme_recognition", "generation_freedom", "composition_mode"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported generator settings: {', '.join(sorted(unknown))}")
        self.config = self.config.model_copy(update=payload)
        self.config = MusicGeneratorConfig.model_validate(self.config.model_dump())
        return self.status()

    async def set_system_mode(self, mode: SystemMode) -> dict:
        self.config = self.config.model_copy(update={"system_mode": mode})
        self.mode_controller.set_mode(mode)
        await self.broadcast({"kind": "mode_changed", "status": self.status()})
        await self._publish_status()
        return self.status()

    def select_theme(self, theme_id: str) -> dict:
        if self.running:
            raise ValueError("stop the generator before changing theme")
        self.theme_library.select(theme_id)
        self.selected_theme_id = theme_id
        self.current_theme = None
        return self.status()

    def randomize_theme(self) -> dict:
        if self.running:
            raise ValueError("stop the generator before changing theme")
        theme = self.theme_library.select("random")
        self.selected_theme_id = theme.id
        self.current_theme = theme
        return self.status()

    def start(self) -> None:
        if self.running:
            return
        self.form.reset()
        self.mode_controller.start()
        self.current_theme = self.theme_library.select(self.selected_theme_id)
        engaging_duration = self.mode_controller.config.ENGAGING.duration_sec
        self.form.configure(self.current_bpm, engaging_duration)
        self.experience_started_at = time.monotonic()
        self.fallback_count = 0
        self.generation_error = ""
        self.task = asyncio.create_task(self._run(), name="theme-music-runtime")
        self.status_task = asyncio.create_task(self._status_heartbeat(), name="music-generator-status")

    async def stop(self) -> None:
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        if self.status_task and self.status_task is not asyncio.current_task():
            self.status_task.cancel()
            try:
                await self.status_task
            except asyncio.CancelledError:
                pass
        self.status_task = None
        for dispatch_task in tuple(self.dispatch_tasks):
            dispatch_task.cancel()
        if self.dispatch_tasks:
            await asyncio.gather(*self.dispatch_tasks, return_exceptions=True)
        self.dispatch_tasks.clear()
        self.playing_segment = None
        self.next_segment = None
        self.segment_started_at = None
        self.all_notes_off()
        await self._publish_status()

    def reload_model(self) -> bool:
        return self.model.load()

    def status(self) -> dict[str, Any]:
        remaining = None
        if self.playing_segment and self.segment_started_at is not None:
            remaining = max(
                0.0,
                self.playing_segment.duration_seconds
                - (time.monotonic() - self.segment_started_at),
            )
        elapsed = (
            time.monotonic() - self.experience_started_at
            if self.experience_started_at is not None
            else 0.0
        )
        position = self.current_position
        theme = self.current_theme
        return {
            "running": self.running,
            "mode": self.config.composition_mode,
            **self.mode_controller.status(),
            "model_provider": self.model.active_provider,
            "model_available": self.model.available,
            "model_loaded": self.model.loaded,
            "model_detail": self.model.detail,
            "window_seconds": self.config.window_seconds,
            "window_samples": self.aggregator.sample_count(),
            "fast_window_seconds": self.config.fast_window_seconds,
            "fast_window_samples": self.fast_aggregator.sample_count(),
            "fast_window_emotion": self.fast_aggregator.aggregate().label,
            "slow_window_emotion": self.aggregator.aggregate().label,
            "current_emotion": self.current_emotion,
            "candidate_emotion": self.candidate_emotion,
            "current_portrait": self.current_emotion,
            "current_motif_id": self.playing_segment.motif_id if self.playing_segment else (self.current_motif.id if self.current_motif else None),
            "current_motif_title": self.playing_segment.motif_title if self.playing_segment else (self.current_motif.title if self.current_motif else None),
            "motif_approved": self.current_motif.approved if self.current_motif else False,
            "segment_source": self.last_segment_source,
            "available_motifs": self.motif_library.list(),
            "available_approved_motifs": self.motif_library.list(approved_only=True),
            "transition_strategy": self.last_transition.strategy if self.last_transition else "",
            "transition_preparing": self.last_transition.preparing if self.last_transition else False,
            "transition_progress": self.last_transition.progress if self.last_transition else 0.0,
            "current_segment_id": self.playing_segment.id if self.playing_segment else None,
            "theme_similarity": (
                self.playing_segment.theme_similarity if self.playing_segment else None
            ),
            "actual_max_voices": (
                self.playing_segment.actual_max_voices if self.playing_segment else 1
            ),
            "harmony_note_count": (
                self.playing_segment.harmony_note_count if self.playing_segment else 0
            ),
            "arpeggio_note_count": (
                self.playing_segment.arpeggio_note_count if self.playing_segment else 0
            ),
            "notochord_modified_count": (
                self.playing_segment.notochord_modified_count
                if self.playing_segment else 0
            ),
            "next_segment_ready": self.next_segment is not None,
            "bpm": self.current_bpm,
            "remaining_seconds": remaining,
            "experience_elapsed_seconds": round(elapsed, 1),
            "last_generation_ms": round(self.last_generation_ms, 2),
            "fallback_count": self.fallback_count,
            "generation_error": self.generation_error,
            "theme_id": theme.id if theme else self.selected_theme_id,
            "theme_title": theme.title if theme else None,
            "available_themes": self.theme_library.list(),
            "form_section": position.section if position else None,
            "phrase_id": position.phrase_id if position else None,
            "phrase_index": position.phrase_index if position else 0,
            "total_phrases": self.form.total_phrases,
            "next_boundary": "phrase",
            "composition_mode": self.config.composition_mode,
            "theme_recognition": self.config.theme_recognition,
            "generation_freedom": self.config.generation_freedom,
        }

    async def _run(self) -> None:
        try:
            self.current_position = self.form.current()
            self.next_segment = await self._generate(self.current_position)
            while not self.form.complete:
                position = self.form.current()
                self.current_position = position
                segment = self.next_segment or await self._generate(position, use_model=False)
                self.next_segment = None
                self.playing_segment = segment
                self.current_emotion = segment.emotion
                self.current_bpm = segment.bpm
                self.segment_started_at = time.monotonic()
                await self._broadcast_structure(position, segment)
                await self.broadcast({
                    "kind": "segment_started",
                    "segment": segment.model_dump(),
                    "status": self.status(),
                })
                self.record_segment(segment)
                dispatch_tasks = self._schedule(segment)
                segment_deadline = self.segment_started_at + segment.duration_seconds
                lookahead_seconds = self.config.lookahead_beats * 60.0 / segment.bpm
                await asyncio.sleep(max(0.0, segment.duration_seconds - lookahead_seconds))
                self.form.advance()
                if not self.form.complete:
                    next_position = self.form.current()
                    self.next_segment = await self._generate(next_position)
                await asyncio.sleep(max(0.0, segment_deadline - time.monotonic()))
                await asyncio.gather(*dispatch_tasks, return_exceptions=True)
            self.all_notes_off()
            self.playing_segment = None
            self.next_segment = None
            await self.broadcast({"kind": "experience_completed", "status": self.status()})
        finally:
            if self.status_task:
                self.status_task.cancel()
            self.status_task = None

    async def _generate(
        self,
        position: FormPosition,
        use_model: bool = True,
    ) -> MusicSegment:
        if self.current_theme is None:
            raise ValueError("no active theme")
        slow_emotion = self.aggregator.aggregate()
        fast_emotion = self.fast_aggregator.aggregate()
        controlled_emotion = self._emotion_for_composition(slow_emotion, fast_emotion)
        self.candidate_emotion = controlled_emotion.label
        fallback_bpm = int(
            self.current_theme.emotion_variants
            .get(controlled_emotion.label, {})
            .get("tempo", self.config.emotion_bpm[controlled_emotion.label])
        )
        target_bpm = self.mode_controller.target_bpm_for(controlled_emotion.label, fallback_bpm)
        bpm = max(
            self.current_bpm - self.config.max_bpm_step,
            min(self.current_bpm + self.config.max_bpm_step, target_bpm),
        )
        started = time.perf_counter()
        self.generation_error = ""
        transition = self.transition_planner.plan(
            self.current_emotion,
            controlled_emotion.label,
            position.section_phrase,
            position.section_changed,
        )
        self.last_transition = transition
        source = self._source_for_position(position)
        motif = self._select_motif(controlled_emotion.label) if source == "motif" else None
        if motif is not None:
            self.current_motif = motif
            segment = self.motif_composer.compose(
                motif,
                position,
                controlled_emotion,
                self.current_emotion,
                bpm,
                self.music_config.tracks,
                self.config.generation_freedom,
                transition,
            )
            self.motif_phrase_count += 1
        else:
            source = "theme"
            self.motif_phrase_count = 0 if self.config.composition_mode == "hybrid" else self.motif_phrase_count
            segment = self.composer.compose(
                self.current_theme,
                position,
                controlled_emotion,
                self.current_emotion,
                bpm,
                self.music_config.tracks,
                self.config.theme_recognition,
                self.config.generation_freedom,
            ).model_copy(update={
                "transition_type": transition.transition_type,
                "from_emotion": transition.from_emotion,
                "to_emotion": transition.to_emotion,
                "transition_progress": transition.progress,
                "transition_strategy": transition.strategy,
            })
        self.last_segment_source = segment.source
        melody_track = next(
            (
                track for track in self.music_config.tracks
                if track.enabled and track.compute_enabled and track.role == "melody"
            ),
            None,
        )
        allow_ornament = (
            use_model
            and melody_track is not None
            and self.model.loaded
            and position.section in {"variation", "development", "climax"}
        )
        if allow_ornament:
            try:
                ornamented = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.model.ornament_segment,
                        segment,
                        controlled_emotion,
                        melody_track,
                        self.config.generation_freedom,
                        self._immutable_beats_for(segment),
                    ),
                    timeout=self.config.inference_timeout_seconds,
                )
                if self.scorer.is_valid(
                    ornamented, melody_track.id, melody_track.pitch_range
                ):
                    segment = ornamented
                else:
                    self.fallback_count += 1
                    self.generation_error = "ornament fallback: invalid polyphonic candidate"
            except Exception as exc:
                self.fallback_count += 1
                self.generation_error = f"ornament fallback: {exc}"
        self.last_generation_ms = (time.perf_counter() - started) * 1000
        segment.generation_ms = self.last_generation_ms
        await self.broadcast({
            "kind": "segment_generated",
            "segment": segment.model_dump(),
            "status": self.status(),
        })
        await self._publish_status()
        return segment

    def _source_for_position(self, position: FormPosition) -> str:
        mode = self.config.composition_mode
        if mode in {"theme", "anchored"}:
            return "theme"
        if mode in {"motif", "generative"}:
            return "motif"
        if position.section in {"intro", "theme", "return", "coda"}:
            return "theme"
        if self.motif_phrase_count >= 2:
            return "theme"
        return "motif"

    def _select_motif(self, emotion: str) -> Motif | None:
        return self.motif_library.select(
            emotion, self.current_motif.id if self.current_motif else None
        )

    def _immutable_beats_for(self, segment: MusicSegment) -> set[float]:
        if segment.motif_id and self.current_motif and segment.motif_id == self.current_motif.id:
            return set(self.current_motif.immutable_beats)
        return set(self.current_theme.immutable_beats if self.current_theme else [])

    def _emotion_for_composition(self, emotion: EmotionState, fast_emotion: EmotionState | None = None) -> EmotionState:
        params = self.mode_controller.music_params
        label = self.mode_controller.composition_label(emotion.label)
        arousal = params.density
        if fast_emotion is not None:
            arousal = max(0.0, min(1.0, arousal * 0.65 + fast_emotion.arousal_norm * 0.35))
        return emotion.model_copy(update={
            "label": label,
            "valence_norm": params.brightness,
            "arousal_norm": arousal,
            "confidence": max(emotion.confidence, self.mode_controller.smoothed_confidence),
        })

    async def _broadcast_structure(
        self,
        position: FormPosition,
        segment: MusicSegment,
    ) -> None:
        status = self.status()
        await self.broadcast({
            "kind": "phrase_started",
            "phrase_id": position.phrase_id,
            "form_section": position.section,
            "segment": segment.model_dump(),
            "status": status,
        })
        if position.section_changed:
            await self.broadcast({
                "kind": "form_section_changed",
                "form_section": position.section,
                "status": status,
            })
        await self.broadcast({
            "kind": "harmony_changed",
            "harmony": segment.harmony,
            "status": status,
        })
        if segment.theme_similarity >= 0.5:
            await self.broadcast({
                "kind": "theme_quoted",
                "theme_id": segment.theme_id,
                "similarity": segment.theme_similarity,
                "status": status,
            })
        if position.section == "climax":
            await self.broadcast({
                "kind": "climax_changed",
                "active": True,
                "status": status,
            })

    def _schedule(self, segment: MusicSegment) -> list[asyncio.Task]:
        tasks: list[asyncio.Task] = []
        seconds_per_beat = 60.0 / segment.bpm
        for note in segment.notes:
            task = asyncio.create_task(self._dispatch_note(note, seconds_per_beat))
            self.dispatch_tasks.add(task)
            task.add_done_callback(self.dispatch_tasks.discard)
            tasks.append(task)
        return tasks

    async def _dispatch_note(self, note, seconds_per_beat: float) -> None:
        await asyncio.sleep(note.beat * seconds_per_beat)
        self.dispatch(MusicEvent(
            timestamp=time.time(),
            track_id=note.track_id,
            type="note_on",
            pitch=note.pitch,
            velocity=note.velocity,
            duration_ms=round(note.duration_beats * seconds_per_beat * 1000),
            channel=note.channel,
        ))
        await asyncio.sleep(note.duration_beats * seconds_per_beat)
        self.dispatch(MusicEvent(
            timestamp=time.time(),
            track_id=note.track_id,
            type="note_off",
            pitch=note.pitch,
            velocity=0,
            duration_ms=0,
            channel=note.channel,
        ))

    def _dispatch_expression(self, emotion: EmotionState) -> None:
        controls = self.mode_controller.expression_controls()
        for track in self.music_config.tracks:
            if not track.enabled or not track.compute_enabled or track.role not in controls:
                continue
            name, value = controls[track.role]
            self.dispatch(MusicEvent(
                track_id=track.id,
                type="control",
                address=f"/music/track/{track.id}/control",
                args=[name, round(max(0.0, min(1.0, value)), 3)],
                channel=track.midi_channel,
            ))
        status = self.status()
        task = asyncio.create_task(
            self.broadcast({"kind": "music_params_changed", "status": status}),
            name="music-params-changed",
        )
        self.dispatch_tasks.add(task)
        task.add_done_callback(self.dispatch_tasks.discard)

    async def _publish_status(self) -> None:
        status = self.status()
        self.record_status(status)
        stage = status.get("engaging_stage")
        if (
            status.get("system_mode") == "ENGAGING"
            and stage
            and stage != self.last_published_stage
        ):
            self.last_published_stage = stage
            await self.broadcast({"kind": "engaging_stage_changed", "status": status})
        await self.broadcast({"kind": "generator_status", "status": status})

    async def _status_heartbeat(self) -> None:
        while True:
            await self._publish_status()
            await asyncio.sleep(1)
