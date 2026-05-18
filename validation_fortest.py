"""Compatibility entry for the OSC validation receiver."""

import argparse

from server.testing.validation_server import run_validation_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--address", default="/eeg/valence_arousal")
    args = parser.parse_args()
    run_validation_server(port=args.port, address=args.address)


if __name__ == "__main__":
    main()

