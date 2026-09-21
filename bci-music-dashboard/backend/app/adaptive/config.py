from __future__ import annotations

import copy
from pathlib import Path
from string import Formatter
from typing import Any
from urllib.parse import urlparse

import yaml


MODULES = (
    "inputs", "policy", "form", "tonal", "motif", "melody",
    "harmony", "orchestration", "outputs",
)


class AdaptiveConfigStore:
    """Validated-by-shape modular configuration with performance locking."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._active = {name: self._load(name) for name in MODULES}
        self._validate_all(self._active)
        self._locked_snapshot: dict[str, Any] | None = None

    @property
    def locked(self) -> bool:
        return self._locked_snapshot is not None

    def all(self) -> dict[str, Any]:
        source = self._locked_snapshot if self.locked else self._active
        return copy.deepcopy(source)

    def get(self, module: str) -> dict[str, Any]:
        self._require_module(module)
        source = self._locked_snapshot if self.locked else self._active
        return copy.deepcopy(source[module])

    def replace(self, module: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_module(module)
        if self.locked:
            raise RuntimeError("performance configuration is locked until the session stops")
        if not isinstance(payload, dict):
            raise ValueError("configuration module must be an object")
        candidate = copy.deepcopy(self._active)
        candidate[module] = copy.deepcopy(payload)
        self._validate_all(candidate)
        self._active[module] = candidate[module]
        self._persist(module, candidate[module])
        return self.get(module)

    def reset(self, module: str) -> dict[str, Any]:
        self._require_module(module)
        if self.locked:
            raise RuntimeError("performance configuration is locked until the session stops")
        self._active[module] = self._load(module)
        return self.get(module)

    def lock(self) -> dict[str, Any]:
        self._locked_snapshot = copy.deepcopy(self._active)
        return self.all()

    def unlock(self) -> None:
        self._locked_snapshot = None

    def export_yaml(self) -> str:
        return yaml.safe_dump(self.all(), allow_unicode=True, sort_keys=False)

    def merge_legacy(self, legacy: dict[str, Any]) -> list[str]:
        if self.locked:
            raise RuntimeError("performance configuration is locked until the session stops")
        from .legacy import merge_legacy_music_config

        candidate, changes = merge_legacy_music_config(self._active, legacy)
        self._validate_all(candidate)
        self._active = candidate
        return changes

    def _load(self, module: str) -> dict[str, Any]:
        path = self.root / f"{module}.yaml"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"{path.name} must contain a YAML object")
        return payload

    def _persist(self, module: str, payload: dict[str, Any]) -> None:
        path = self.root / f"{module}.yaml"
        temporary = path.with_suffix(".yaml.tmp")
        temporary.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _validate_all(config: dict[str, dict[str, Any]]) -> None:
        missing = [name for name in MODULES if not isinstance(config.get(name), dict)]
        if missing:
            raise ValueError(f"missing configuration modules: {', '.join(missing)}")

        inputs = config["inputs"]
        if inputs.get("strategy") != "adaptive_performance":
            raise ValueError("inputs.strategy must be adaptive_performance")
        weather = inputs.get("weather", {})
        if weather.get("enabled") and (weather.get("latitude") is None or weather.get("longitude") is None):
            raise ValueError("enabled weather requires explicit latitude and longitude")
        if float(weather.get("timeout_seconds", 1.5)) > 1.5:
            raise ValueError("weather timeout_seconds must not exceed 1.5")

        weights = config["policy"].get("weights", {})
        for group, bci_key in (("energy", "bci_arousal"), ("pulse", "bci_arousal"), ("brightness", "bci_valence")):
            values = weights.get(group, {})
            primary = float(values.get(bci_key, 0.0))
            auxiliary = sum(max(0.0, float(value)) for key, value in values.items() if key != bci_key)
            if primary <= 0 or primary < auxiliary:
                raise ValueError(f"policy.weights.{group} must remain BCI-led")

        form = config["form"]
        sections = form.get("sections", [])
        minimum_phrases = int(form.get("minimum_phrases_per_section", 0))
        maximum_phrases = int(form.get("maximum_phrases_per_section", 0))
        if not sections or minimum_phrases < 2:
            raise ValueError("form requires sections and at least two phrases per section")
        if maximum_phrases < minimum_phrases:
            raise ValueError("form maximum_phrases_per_section must be at least the minimum")
        transition_confidence = float(form.get("transition_confidence", -1))
        if not 0.0 <= transition_confidence <= 1.0:
            raise ValueError("form transition_confidence must be between 0 and 1")
        ids = [str(section.get("id", "")) for section in sections]
        if not all(ids) or len(ids) != len(set(ids)):
            raise ValueError("form section ids must be non-empty and unique")
        roles = {"intro", "identity", "contrast", "development", "climax", "return", "coda"}
        invalid_roles = [str(section.get("role", "")) for section in sections if section.get("role") not in roles]
        if invalid_roles:
            raise ValueError(f"unknown form roles: {sorted(set(invalid_roles))}")
        transitions = form.get("transitions", {})
        if set(transitions) != set(ids):
            raise ValueError("form transitions must define every section id exactly once")
        unknown_targets = {
            target for targets in transitions.values() for target in targets if target not in ids
        }
        if unknown_targets:
            raise ValueError(f"unknown form transition targets: {sorted(unknown_targets)}")
        for index, section_id in enumerate(ids[:-1]):
            next_id = ids[index + 1]
            targets = set(transitions[section_id])
            if next_id not in targets or targets - {section_id, next_id}:
                raise ValueError(
                    f"form transition {section_id} must allow only itself and the next section {next_id}"
                )
        if transitions[ids[-1]]:
            raise ValueError("the final form section must have no outgoing transitions")

        tonal = config["tonal"]
        low, high = tonal.get("melody_range", [48, 84])
        if not (0 <= int(low) < int(high) <= 127):
            raise ValueError("tonal.melody_range must be an ascending MIDI range")
        for name in (tonal.get("positive_scale"), tonal.get("negative_scale"), tonal.get("neutral_scale")):
            if name not in tonal.get("scales", {}):
                raise ValueError(f"unknown tonal scale: {name}")

        motif = config["motif"]
        motif_bars = int(motif.get("bars", 0))
        motif_beats_per_bar = int(motif.get("beats_per_bar", 0))
        if not 1 <= motif_bars <= 4 or not 1 <= motif_beats_per_bar <= 12:
            raise ValueError("motif bars and beats_per_bar are out of range")
        if motif_beats_per_bar != int(form.get("beats_per_bar", 4)):
            raise ValueError("motif and form beats_per_bar must match")
        subdivisions = [float(value) for value in motif.get("allowed_subdivisions", [])]
        if not subdivisions or any(value <= 0 or value > motif_beats_per_bar for value in subdivisions):
            raise ValueError("motif.allowed_subdivisions must contain positive beat values within one bar")
        density_thresholds = motif.get("density_thresholds", {})
        medium_above = float(density_thresholds.get("medium_above", -1))
        fast_above = float(density_thresholds.get("fast_above", -1))
        if not 0 <= medium_above < fast_above <= 1:
            raise ValueError("motif density thresholds must satisfy 0 <= medium_above < fast_above <= 1")
        valence_thresholds = motif.get("valence_thresholds", {})
        low_below = float(valence_thresholds.get("low_below", -1))
        high_above = float(valence_thresholds.get("high_above", -1))
        if not 0 <= low_below < high_above <= 1:
            raise ValueError("motif valence thresholds must satisfy 0 <= low_below < high_above <= 1")
        allowed_contours = {"ascending", "descending", "wave"}
        contours = motif.get("contours", {})
        if set(contours) != {"low_valence", "neutral", "high_valence"} or any(
            value not in allowed_contours for value in contours.values()
        ):
            raise ValueError("motif.contours must define valid low, neutral, and high valence contours")
        total_beats = motif_bars * motif_beats_per_bar
        anchors = [float(value) for value in motif.get("anchors", {}).get("beats", [])]
        if any(value < 0 or value >= total_beats for value in anchors):
            raise ValueError("motif anchor beats must fall within the motif")
        allowed_transforms = {"simplify", "identity", "transpose", "invert", "compress", "recall", "cadence"}
        transforms = motif.get("transform_by_form", {})
        if set(transforms) != roles or any(value not in allowed_transforms for value in transforms.values()):
            raise ValueError("motif.transform_by_form must define a valid transform for every form role")
        transform_settings = motif.get("transform_settings", {})
        if int(transform_settings.get("simplify_stride", 0)) < 1:
            raise ValueError("motif simplify_stride must be at least 1")
        if not -7 <= int(transform_settings.get("transpose_scale_steps", 0)) <= 7:
            raise ValueError("motif transpose_scale_steps must be between -7 and 7")
        if not 0 < float(transform_settings.get("compression_ratio", 0)) <= 1:
            raise ValueError("motif compression_ratio must be between 0 and 1")
        if float(transform_settings.get("cadence_duration_beats", 0)) <= 0:
            raise ValueError("motif cadence_duration_beats must be positive")

        melody = config["melody"]
        worker_url = str(melody.get("worker_url", ""))
        parsed = urlparse(worker_url)
        if parsed.scheme not in {"ws", "wss"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("melody.worker_url must be a localhost WebSocket URL")
        if float(melody.get("frame_hz", 25)) != 25:
            raise ValueError("MRT2 conditioning frame_hz must be 25")
        prompt_template = str(melody.get("prompt_template", ""))
        if not prompt_template.strip():
            raise ValueError("melody.prompt_template must not be empty")
        allowed_prompt_fields = {"mood", "energy", "articulation", "form"}
        try:
            prompt_fields = {
                field_name
                for _, field_name, _, _ in Formatter().parse(prompt_template)
                if field_name is not None
            }
        except ValueError as exc:
            raise ValueError(f"invalid melody.prompt_template: {exc}") from exc
        unknown_prompt_fields = prompt_fields - allowed_prompt_fields
        if "" in prompt_fields or unknown_prompt_fields:
            invalid = sorted(unknown_prompt_fields | ({"positional field"} if "" in prompt_fields else set()))
            raise ValueError(f"unknown melody prompt fields: {invalid}")
        transcription = melody.get("transcription", {})
        transcription_range = transcription.get("pitch_range", [])
        if not isinstance(transcription_range, list) or len(transcription_range) != 2:
            raise ValueError("melody.transcription.pitch_range must contain two MIDI notes")
        transcription_low, transcription_high = map(int, transcription_range)
        if not 0 <= transcription_low < transcription_high <= 127:
            raise ValueError("melody.transcription.pitch_range must be an ascending MIDI range")
        if int(transcription.get("stable_frames", 0)) < 1:
            raise ValueError("melody.transcription.stable_frames must be at least 1")
        if int(transcription.get("minimum_note_ms", 0)) < 1:
            raise ValueError("melody.transcription.minimum_note_ms must be positive")
        guardrails = melody.get("guardrails", {})
        if guardrails.get("soft_grid") not in {"1/4", "1/8", "1/16"}:
            raise ValueError("melody.guardrails.soft_grid must be 1/4, 1/8, or 1/16")
        if float(guardrails.get("snap_tolerance_ms", -1)) < 0:
            raise ValueError("melody.guardrails.snap_tolerance_ms must not be negative")

        harmony = config["harmony"]
        if harmony.get("provider", "rule") != "rule":
            raise ValueError("harmony.provider must be rule")
        allowed_chords = {"I", "ii", "iii", "IV", "V", "vi", "vii°"}
        progressions = harmony.get("progressions", {})
        if not progressions or any(
            not progression or any(symbol not in allowed_chords for symbol in progression)
            for progression in progressions.values()
        ):
            raise ValueError("harmony progressions must contain supported Roman-numeral chords")
        notochord = harmony.get("notochord", {})
        if any(role not in {"harmony", "bass", "inner_voice"} for role in notochord.get("roles", [])):
            raise ValueError("harmony.notochord.roles contains an unsupported role")
        if float(notochord.get("timeout_seconds", 0.20)) <= 0:
            raise ValueError("harmony.notochord.timeout_seconds must be positive")
        counterpoint = harmony.get("counterpoint", {})
        maximum_voices = int(counterpoint.get("maximum_voices", 2))
        if not 1 <= maximum_voices <= 2:
            raise ValueError("v1 counterpoint supports one or two voices")
        if any(role not in roles for role in counterpoint.get("forms", [])):
            raise ValueError("harmony.counterpoint.forms contains an unknown form role")
        if float(counterpoint.get("entry_delay_beats", 0)) < 0:
            raise ValueError("harmony.counterpoint.entry_delay_beats must not be negative")
        if not -24 <= int(counterpoint.get("interval_semitones", 0)) <= 24:
            raise ValueError("harmony.counterpoint.interval_semitones must be between -24 and 24")

        outputs = config["outputs"]
        if int(outputs.get("audio", {}).get("sample_rate", 48_000)) != 48_000:
            raise ValueError("MRT2 audio output sample_rate must be 48000")
        for role, channel in outputs.get("midi", {}).get("channels", {}).items():
            if not 1 <= int(channel) <= 16:
                raise ValueError(f"invalid MIDI channel for {role}: {channel}")
        for target in outputs.get("osc", {}).get("targets", []):
            if not target.get("id") or not target.get("host") or not 1 <= int(target.get("port", 0)) <= 65535:
                raise ValueError("every OSC target requires id, host, and a valid port")

    @staticmethod
    def _require_module(module: str) -> None:
        if module not in MODULES:
            raise KeyError(module)
