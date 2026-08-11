from __future__ import annotations

from magenta_flow.midi_io import MidiOutput, select_midi_port
from magenta_flow.transcription import NoteEvent


class FakePort:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, message):
        self.messages.append(message)

    def close(self):
        self.closed = True


def test_selects_iac_by_default_and_unique_substring():
    ports = ["External Keyboard", "IAC Driver Bus 1"]
    assert select_midi_port(ports, None) == "IAC Driver Bus 1"
    assert select_midi_port(ports, "Bus 1") == "IAC Driver Bus 1"


def test_midi_output_sends_channel_and_panic_cleanup():
    port = FakePort()
    output = MidiOutput(port, channel=2)
    output.send(NoteEvent("note_on", 69, 100, 0.0))
    output.send(NoteEvent("note_off", 69, 0, 0.2))
    output.close()

    assert port.messages[0].type == "note_on"
    assert port.messages[0].channel == 1
    assert port.messages[1].type == "note_off"
    controls = [message.control for message in port.messages if message.type == "control_change"]
    assert controls == [123, 120]
    assert port.closed


def test_midi_output_defensively_closes_previous_note():
    port = FakePort()
    output = MidiOutput(port)
    output.send(NoteEvent("note_on", 60, 80, 0.0))
    output.send(NoteEvent("note_on", 64, 80, 0.1))
    assert [(message.type, getattr(message, "note", None)) for message in port.messages] == [
        ("note_on", 60),
        ("note_off", 60),
        ("note_on", 64),
    ]

