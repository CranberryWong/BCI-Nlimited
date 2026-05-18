from __future__ import annotations

import argparse
import random
import time

from pythonosc import udp_client


def run_sender(ip: str = "127.0.0.1", port: int = 8000, address: str = "/eeg/valence_arousal") -> None:
    client = udp_client.SimpleUDPClient(ip, int(port))
    print(f"Fake OSC sender -> {ip}:{port} {address}")
    try:
        while True:
            valence = random.randint(1, 9)
            arousal = random.randint(1, 9)
            prob0 = round(random.uniform(0.1, 0.9), 2)
            prob1 = round(1 - prob0, 2)
            payload = [valence, arousal, prob0, prob1]
            client.send_message(address, payload)
            print(f"Sent -> {payload}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Sender stopped")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--address", default="/eeg/valence_arousal")
    args = parser.parse_args()
    run_sender(args.ip, args.port, args.address)


if __name__ == "__main__":
    main()

