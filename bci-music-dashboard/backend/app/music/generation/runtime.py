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
from app.music.generation.portrait_composer import PortraitComposer
from app.music.generation.portrait_library import PortraitAsset, PortraitLibrary
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
    INITIAL_SAMPLE_CONFIDENCE = 0.45
    TENSION_ENTER_AROUSAL = 0.68
    TENSION_HOLD_AROUSAL = 0.48
    RELEASE_AROUSAL = 0.32
    def __init__(
        self,
        config: MusicGeneratorConfig,
        music_config: ActiveMusicConfig,
        model: MelodyModel,
        theme_library: ThemeLibrary,
        motif_library: MotifLibrary,
        portrait_library: PortraitLibrary,
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
        self.portrait_library = portrait_library
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
        self.portrait_composer = PortraitComposer()
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
        self.current_portrait_asset: PortraitAsset | None = None
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
        self.xylophone_last_note_on: dict[int, float] = {}
        self.xylophone_suppressed_count = 0
        self.initial_emotion_ready = False
        self.active_portrait_emotion: str | None = None
        self.pending_portrait_emotion: str | None = None
        self.next_portrait_role = "loop"
        self.portrait_phrase_index = 0
        self.last_portrait_role = "loop"
        self.portrait_harmony_enabled = False
        self.portrait_harmony_arpeggio_enabled = False

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def add_emotion(self, emotion: EmotionState) -> None:
        if self.config.composition_mode != "portrait" or emotion.confidence >= self.INITIAL_SAMPLE_CONFIDENCE:
            self.aggregator.add(emotion)
        self.fast_aggregator.add(emotion)
        self.mode_controller.update_emotion(emotion)
        if self.running:
            if self.config.composition_mode == "portrait":
                self._dispatch_portrait_expression(emotion)
            else:
                self._dispatch_expression(emotion)

    def update_music_config(self, music_config: ActiveMusicConfig) -> None:
        self.music_config = music_config
        self.mode_controller.configure(music_config.system_modes)

    def update_settings(self, payload: dict[str, Any]) -> dict:
        if "portrait_harmony_enabled" in payload:
            if set(payload) != {"portrait_harmony_enabled"}:
                raise ValueError("portrait_harmony_enabled must be updated on its own")
            value = payload["portrait_harmony_enabled"]
            if not isinstance(value, bool):
                raise ValueError("portrait_harmony_enabled must be a boolean")
            self.portrait_harmony_enabled = value
            if not value:
                self.portrait_harmony_arpeggio_enabled = False
            return self.status()
        if "portrait_harmony_arpeggio_enabled" in payload:
            if set(payload) != {"portrait_harmony_arpeggio_enabled"}:
                raise ValueError("portrait_harmony_arpeggio_enabled must be updated on its own")
            value = payload["portrait_harmony_arpeggio_enabled"]
            if not isinstance(value, bool):
                raise ValueError("portrait_harmony_arpeggio_enabled must be a boolean")
            self.portrait_harmony_arpeggio_enabled = value and self.portrait_harmony_enabled
            return self.status()
        if self.config.composition_mode == "portrait":
            raise ValueError("portrait runtime only exposes portrait harmony settings")
        allowed = {"theme_recognition", "generation_freedom", "composition_mode"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported generator settings: {', '.join(sorted(unknown))}")
        self.config = self.config.model_copy(update=payload)
        self.config = MusicGeneratorConfig.model_validate(self.config.model_dump())
        return self.status()

    async def set_system_mode(self, mode: SystemMode) -> dict:
        if self.config.composition_mode == "portrait":
            raise ValueError("portrait runtime does not expose MIRROR or ENGAGING modes")
        self.config = self.config.model_copy(update={"system_mode": mode})
        self.mode_controller.set_mode(mode)
        await self.broadcast({"kind": "mode_changed", "status": self.status()})
        await self._publish_status()
        return self.status()

    def select_theme(self, theme_id: str) -> dict:
        if self.config.composition_mode == "portrait":
            raise ValueError("portrait runtime does not use themes")
        if self.running:
            raise ValueError("stop the generator before changing theme")
        self.theme_library.select(theme_id)
        self.selected_theme_id = theme_id
        self.current_theme = None
        return self.status()

    def randomize_theme(self) -> dict:
        if self.config.composition_mode == "portrait":
            raise ValueError("portrait runtime does not use themes")
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
        if self.config.composition_mode != "portrait":
            self.current_theme = self.theme_library.select(self.selected_theme_id)
            engaging_duration = self.mode_controller.config.ENGAGING.duration_sec
            self.form.configure(self.current_bpm, engaging_duration)
        self.experience_started_at = time.monotonic()
        self.fallback_count = 0
        self.generation_error = ""
        self.current_motif = None
        self.current_portrait_asset = None
        self.xylophone_last_note_on = {}
        self.xylophone_suppressed_count = 0
        self.initial_emotion_ready = False
        self.active_portrait_emotion = None
        self.pending_portrait_emotion = None
        self.next_portrait_role = "loop"
        self.portrait_phrase_index = 0
        self.last_portrait_role = "loop"
        self.portrait_harmony_enabled = False
        self.portrait_harmony_arpeggio_enabled = False
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
        current_harmony_index = None
        current_harmony = ""
        if self.playing_segment and self.segment_started_at is not None and self.playing_segment.harmony:
            elapsed_beats = (time.monotonic() - self.segment_started_at) * self.playing_segment.bpm / 60.0
            current_harmony_index = min(
                int(elapsed_beats // self.playing_segment.beats_per_bar),
                len(self.playing_segment.harmony) - 1,
            )
            current_harmony = self.playing_segment.harmony[current_harmony_index]
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
            "initial_emotion_ready": self.initial_emotion_ready,
            "required_initial_samples": self.config.minimum_samples,
            "active_portrait_emotion": self.active_portrait_emotion,
            "pending_portrait_emotion": self.pending_portrait_emotion,
            "next_portrait_role": self.next_portrait_role,
            "current_portrait_asset_id": self.playing_segment.portrait_asset_id if self.playing_segment else (self.current_portrait_asset.id if self.current_portrait_asset else ""),
            "current_portrait_asset_title": self.playing_segment.portrait_asset_title if self.playing_segment else (self.current_portrait_asset.title if self.current_portrait_asset else ""),
            "portrait_role": self.playing_segment.portrait_role if self.playing_segment else (self.current_portrait_asset.role if self.current_portrait_asset else ""),
            "portrait_harmony_enabled": self.portrait_harmony_enabled,
            "portrait_harmony_arpeggio_enabled": self.portrait_harmony_arpeggio_enabled,
            "current_harmony": current_harmony,
            "current_harmony_index": current_harmony_index,
            "harmony_progression": self.playing_segment.harmony if self.playing_segment else [],
            "available_portrait_assets": self.portrait_library.list(),
            "portrait_library_errors": self.portrait_library.errors,
            "xylophone_same_key_minimum_interval_seconds": 1.0,
            "xylophone_suppressed_count": self.xylophone_suppressed_count,
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
            "notochord_track_counts": (
                self.playing_segment.notochord_track_counts if self.playing_segment else {}
            ),
            "notochord_tracks": self._portrait_notochord_status(),
            "base_bpm": self.music_config.global_settings.bpm,
            "effective_bpm": self.playing_segment.bpm if self.playing_segment else self.current_bpm,
            "next_target_bpm": (
                self.playing_segment.target_bpm if self.playing_segment else None
            ),
            "bass_note_count": self.playing_segment.bass_note_count if self.playing_segment else 0,
            "drum_note_count": self.playing_segment.drum_note_count if self.playing_segment else 0,
            "cymbal_note_count": self.playing_segment.cymbal_note_count if self.playing_segment else 0,
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
            if self.config.composition_mode == "portrait":
                await self._run_portrait()
                return
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

    async def _run_portrait(self) -> None:
        while not self.initial_emotion_ready:
            if self.aggregator.sample_count() >= self.config.minimum_samples:
                initial = self.aggregator.aggregate()
                self.initial_emotion_ready = True
                self.active_portrait_emotion = initial.label
                self.current_emotion = initial.label
                self.candidate_emotion = initial.label
                self.next_portrait_role = "loop"
                break
            await asyncio.sleep(0.2)

        while True:
            slow_emotion = self.aggregator.aggregate()
            fast_emotion = self.fast_aggregator.aggregate()
            role = self._portrait_role_for(slow_emotion, fast_emotion)
            active = self.active_portrait_emotion or slow_emotion.label
            asset = self.portrait_library.select(active, role)
            if asset is None:
                self.generation_error = f"missing portrait asset: {active}/{role}"
                await self._publish_status()
                await asyncio.sleep(0.5)
                continue

            position = self._portrait_position(role)
            composed_emotion = slow_emotion.model_copy(update={"label": active})
            base_bpm = self.music_config.global_settings.bpm
            effective_bpm, target_bpm = self.portrait_composer.arranger.effective_bpm(
                base_bpm,
                active,
                self.current_bpm if self.playing_segment else None,
            )
            self.current_position = position
            self.current_portrait_asset = asset
            segment = self.portrait_composer.compose(
                asset,
                position,
                composed_emotion,
                self.current_emotion,
                self.music_config.tracks,
                bpm=effective_bpm,
                harmony_enabled=self.portrait_harmony_enabled,
                harmony_arpeggio_enabled=self.portrait_harmony_arpeggio_enabled,
            )
            segment = segment.model_copy(update={"base_bpm": base_bpm, "target_bpm": target_bpm})
            try:
                assisted = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.model.assist_portrait_segment,
                        segment,
                        self.music_config.tracks,
                    ),
                    timeout=self.config.inference_timeout_seconds,
                )
                if self._portrait_assist_is_valid(segment, assisted):
                    segment = assisted
                elif assisted is not segment:
                    self.fallback_count += 1
                    self.generation_error = "portrait Notochord fallback: immutable note changed"
            except Exception as exc:
                self.fallback_count += 1
                self.generation_error = f"portrait Notochord fallback: {exc}"
            self.last_segment_source = segment.source
            self.last_generation_ms = segment.generation_ms
            self.next_segment = None
            self.playing_segment = segment
            self.current_emotion = active
            self.current_bpm = segment.bpm
            self.segment_started_at = time.monotonic()
            self.next_portrait_role = role
            self.last_portrait_role = role
            await self.broadcast({"kind": "segment_generated", "segment": segment.model_dump(), "status": self.status()})
            await self.broadcast({"kind": "segment_started", "segment": segment.model_dump(), "status": self.status()})
            self.record_segment(segment)
            dispatch_tasks = self._schedule(segment)
            await asyncio.sleep(segment.duration_seconds)
            await asyncio.gather(*dispatch_tasks, return_exceptions=True)
            self.portrait_phrase_index += 1

            if role == "release":
                if self.pending_portrait_emotion is not None:
                    self.active_portrait_emotion = self.pending_portrait_emotion
                    self.current_emotion = self.pending_portrait_emotion
                    self.pending_portrait_emotion = None
                self.next_portrait_role = "loop"
                self.last_portrait_role = "release"

    def _portrait_role_for(self, slow: EmotionState, fast: EmotionState) -> str:
        active = self.active_portrait_emotion
        if active is None:
            return "loop"
        if slow.label != active:
            self.pending_portrait_emotion = slow.label
            self.next_portrait_role = "release"
            return "release"
        if self.last_portrait_role == "release":
            self.next_portrait_role = "loop"
            return "loop"
        if self.last_portrait_role == "tension":
            if fast.arousal_norm <= self.RELEASE_AROUSAL:
                self.next_portrait_role = "release"
                return "release"
            if fast.arousal_norm >= self.TENSION_HOLD_AROUSAL:
                self.next_portrait_role = "tension"
                return "tension"
        if fast.arousal_norm >= self.TENSION_ENTER_AROUSAL:
            self.next_portrait_role = "tension"
            return "tension"
        self.next_portrait_role = "loop"
        return "loop"

    def _portrait_position(self, role: str) -> FormPosition:
        section = {"loop": "theme", "tension": "climax", "release": "coda"}[role]
        return FormPosition(
            section=section,
            phrase_id=f"portrait-{self.portrait_phrase_index + 1}",
            phrase_index=self.portrait_phrase_index,
            section_phrase=0,
            section_changed=True,
            is_final=False,
        )

    async def _generate(
        self,
        position: FormPosition,
        use_model: bool = True,
    ) -> MusicSegment:
        if self.current_theme is None and self.config.composition_mode != "portrait":
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
        portrait_asset = self._select_portrait(controlled_emotion.label, position) if source == "portrait" else None
        if portrait_asset is not None:
            self.current_portrait_asset = portrait_asset
            segment = self.portrait_composer.compose(
                portrait_asset, position, controlled_emotion, self.current_emotion, self.music_config.tracks,
            )
            self.current_bpm = segment.bpm
            self.last_segment_source = segment.source
            self.last_generation_ms = (time.perf_counter() - started) * 1000
            segment.generation_ms = self.last_generation_ms
            await self.broadcast({"kind": "segment_generated", "segment": segment.model_dump(), "status": self.status()})
            await self._publish_status()
            return segment
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
        if mode == "portrait":
            return "portrait"
        if mode in {"theme", "anchored"}:
            return "theme"
        if mode in {"motif", "generative"}:
            return "motif"
        if position.section in {"intro", "theme", "return", "coda"}:
            return "theme"
        if self.motif_phrase_count >= 2:
            return "theme"
        return "motif"

    def _select_portrait(self, emotion: str, position: FormPosition) -> PortraitAsset | None:
        role = "loop"
        if position.section in {"variation", "development", "climax"}:
            role = "tension"
        elif position.section == "coda" or (position.section_changed and emotion != self.current_emotion):
            role = "release"
        asset = self.portrait_library.select(emotion, role)
        if asset is None and role != "loop":
            asset = self.portrait_library.select(emotion, "loop")
        return asset

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
            task = asyncio.create_task(self._dispatch_note(note, seconds_per_beat, note.track_id == self._melody_track_id()))
            self.dispatch_tasks.add(task)
            task.add_done_callback(self.dispatch_tasks.discard)
            tasks.append(task)
        return tasks

    def _melody_track_id(self) -> str | None:
        return next((track.id for track in self.music_config.tracks if track.enabled and track.compute_enabled and track.role == "melody"), None)

    def _portrait_notochord_status(self) -> dict[str, dict[str, object]]:
        available = self.model.active_provider == "notochord" and self.model.loaded
        return {
            track.id: {
                "enabled": bool(getattr(track, "notochord_enabled", False)),
                "mode": str(getattr(track, "notochord_mode", "off")),
                "available": available and isinstance(getattr(track, "notochord_instrument", None), int),
            }
            for track in self.music_config.tracks
        }

    @staticmethod
    def _portrait_assist_is_valid(original: MusicSegment, candidate: MusicSegment) -> bool:
        original_authored = [
            note.model_dump() for note in original.notes
            if not note.notochord_eligible
        ]
        candidate_authored = [
            note.model_dump() for note in candidate.notes
            if not note.notochord_eligible
        ]
        return original_authored == candidate_authored

    async def _dispatch_note(self, note, seconds_per_beat: float, is_xylophone: bool) -> None:
        await asyncio.sleep(note.beat * seconds_per_beat)
        if is_xylophone:
            now = time.monotonic()
            previous = self.xylophone_last_note_on.get(note.pitch)
            if previous is not None and now - previous < .999:
                self.xylophone_suppressed_count += 1
                return
            self.xylophone_last_note_on[note.pitch] = now
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

    def _dispatch_portrait_expression(self, emotion: EmotionState) -> None:
        arousal = max(0.0, min(1.0, emotion.arousal_norm))
        valence = max(0.0, min(1.0, emotion.valence_norm))
        controls = {
            "melody": ("expression", 0.30 + arousal * 0.60),
            "pad": ("brightness", 0.25 + valence * 0.65),
            "bass": ("intensity", 0.20 + arousal * 0.50),
            "drum": ("intensity", arousal * 0.75),
            "cymbal": ("brightness", 0.15 + arousal * 0.65),
        }
        for track in self.music_config.tracks:
            if not track.enabled or not track.compute_enabled or track.role not in controls:
                continue
            name, value = controls[track.role]
            self.dispatch(MusicEvent(
                track_id=track.id,
                type="control",
                address=f"/music/track/{track.id}/control",
                args=[name, round(value, 3)],
                channel=track.midi_channel,
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
