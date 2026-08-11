from __future__ import annotations

import copy
from typing import Any


ROLE_MAP = {
    "melody": "marimba",
    "chord": "harmony",
    "bass": "bass",
    "drum": "snare",
    "cymbal": "cymbal",
    "pad": "pad",
    "fx": "fx",
}


def merge_legacy_music_config(adaptive: dict[str, Any], legacy: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Import useful legacy defaults without restoring per-track routing at runtime.

    Network endpoints become disabled central OutputHub targets so an operator can
    review them before enabling. Existing adaptive values always win.
    """
    result = copy.deepcopy(adaptive)
    changes: list[str] = []
    tracks = legacy.get("default_tracks", [])
    channels = result["outputs"].setdefault("midi", {}).setdefault("channels", {})
    targets = result["outputs"].setdefault("osc", {}).setdefault("targets", [])
    known_endpoints = {(str(item.get("host")), int(item.get("port", 0))) for item in targets}
    roles = result["orchestration"].setdefault("roles", {})

    for track in tracks:
        role = ROLE_MAP.get(str(track.get("role", "")))
        if not role:
            continue
        channel = track.get("midi_channel")
        if role not in channels and channel is not None:
            channels[role] = int(channel)
            changes.append(f"midi channel: {role}")
        if role not in roles:
            roles[role] = {
                "enabled": bool(track.get("enabled", True)),
                "base_density": float(track.get("density", 0.3)),
                "base_velocity": round(sum(track.get("velocity_range", [40, 80])) / 2),
            }
            changes.append(f"orchestration role: {role}")
        host = track.get("target_ip")
        port = track.get("target_port")
        endpoint = (str(host), int(port or 0))
        if host and port and endpoint not in known_endpoints:
            target_id = f"legacy-{str(host).replace('.', '-')}-{port}"
            targets.append({
                "id": target_id,
                "host": str(host),
                "port": int(port),
                "enabled": False,
                "migrated_from_track_routing": True,
            })
            known_endpoints.add(endpoint)
            changes.append(f"disabled OSC target: {host}:{port}")

    return result, changes
