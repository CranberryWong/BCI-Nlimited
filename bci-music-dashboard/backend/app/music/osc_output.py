from __future__ import annotations

from pythonosc.udp_client import SimpleUDPClient

from app.music.schemas import EmotionState, MusicEvent, TrackConfig


class OscOutput:
    def __init__(self) -> None:
        self._clients: dict[tuple[str, int], SimpleUDPClient] = {}

    def send_event(self, track: TrackConfig, event: MusicEvent) -> None:
        client = self._client(track.target_ip, track.target_port)
        try:
            if event.type in {"note_on", "note_off"}:
                address = f"/music/track/{track.id}/note"
                client.send_message(address, [event.type, event.pitch or 0, event.velocity or 0, event.duration_ms or 0, event.channel or track.midi_channel])
            else:
                address = event.address or f"/music/track/{track.id}/control"
                client.send_message(address, event.args)
        except OSError:
            return

    def send_emotion(self, track: TrackConfig, emotion: EmotionState) -> None:
        try:
            self._client(track.target_ip, track.target_port).send_message(
                "/music/emotion",
                [emotion.label, emotion.valence_class, emotion.arousal_class, emotion.valence_prob, emotion.arousal_prob],
            )
        except OSError:
            return

    def _client(self, ip: str, port: int) -> SimpleUDPClient:
        key = (ip, port)
        if key not in self._clients:
            self._clients[key] = SimpleUDPClient(ip, port)
        return self._clients[key]
