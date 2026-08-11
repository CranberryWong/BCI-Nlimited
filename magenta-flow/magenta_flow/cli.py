from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .midi_io import MidiOutput, list_midi_ports, select_midi_port
from .pipeline import run_pipeline, validate_resources


DEFAULT_PROMPT = "Joyful fast solo marimba melody, single notes only"
DEFAULT_MAGENTA_HOME = Path.home() / "Documents" / "Magenta" / "magenta-rt-v2"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate MRT2 audio, transcribe one melody, and send MIDI to Logic Pro."
    )
    parser.add_argument("--prompt", help="MRT2 text prompt; omit for interactive input")
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Run length in seconds; 0 runs until Ctrl+C (default: 30)",
    )
    parser.add_argument("--model", default="mrt2_small")
    parser.add_argument(
        "--magenta-home", type=Path, default=DEFAULT_MAGENTA_HOME
    )
    parser.add_argument("--midi-port", help="Exact name or unique substring")
    parser.add_argument(
        "--midi-channel", type=int, default=1, help="Logic MIDI channel, 1..16"
    )
    parser.add_argument(
        "--play-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Monitor MRT2's raw audio (default: enabled)",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--style-strength", type=float, default=2.4)
    parser.add_argument(
        "--list-midi-ports", action="store_true", help="List outputs and exit"
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate model resources and MIDI routing"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.duration < 0:
        raise SystemExit("--duration must be zero or positive")
    if not 1 <= args.midi_channel <= 16:
        raise SystemExit("--midi-channel must be in 1..16")

    try:
        ports = list_midi_ports()
        if args.list_midi_ports:
            if ports:
                print("Available MIDI outputs:")
                for name in ports:
                    print(f"  - {name}")
            else:
                print("No MIDI outputs detected.")
            return 0

        resources = validate_resources(args.magenta_home, args.model)
        port_name = select_midi_port(ports, args.midi_port)
        if args.check:
            print(f"MRT2 resources: OK ({len(resources)} required files)")
            print(f"MIDI output: {port_name}")
            return 0

        prompt = args.prompt
        if prompt is None:
            entered = input(f"Prompt [{DEFAULT_PROMPT}]: ").strip()
            prompt = entered or DEFAULT_PROMPT

        print(f"Model: {args.model}")
        print(f"Prompt: {prompt}")
        print(f"MIDI: {port_name}, channel {args.midi_channel}")
        print("MIDI output is forced monophonic. Press Ctrl+C to stop safely.")

        midi_output = MidiOutput.open(port_name, args.midi_channel)
        summary = run_pipeline(
            magenta_home=args.magenta_home,
            model_name=args.model,
            prompt=prompt,
            duration=args.duration,
            temperature=args.temperature,
            top_k=args.top_k,
            style_strength=args.style_strength,
            midi_output=midi_output,
            output_dir=Path(__file__).resolve().parents[1] / "outputs",
            midi_channel=args.midi_channel,
            play_audio=args.play_audio,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Finished.")
    print(
        f"Frames: {summary.frames}; MIDI events: {summary.midi_events}; "
        f"queue underruns: {summary.queue_underruns}"
    )
    print(
        f"Model timing: average {summary.average_model_ms:.1f} ms, "
        f"max {summary.maximum_model_ms:.1f} ms (target <= 40 ms)"
    )
    print(f"WAV:  {summary.artifacts.wav}")
    print(f"MIDI: {summary.artifacts.midi}")
    print(f"CSV:  {summary.artifacts.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

