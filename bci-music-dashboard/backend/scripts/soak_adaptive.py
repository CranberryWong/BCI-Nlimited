from __future__ import annotations

import argparse
import json
import time
import urllib.request


def request(base_url: str, path: str, method: str = "GET") -> dict:
    raw = urllib.request.Request(f"{base_url.rstrip('/')}{path}", method=method)
    with urllib.request.urlopen(raw, timeout=3.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Two-hour acceptance monitor for adaptive performance")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--duration-seconds", type=float, default=7200)
    parser.add_argument("--poll-seconds", type=float, default=5)
    args = parser.parse_args()
    failures: list[str] = []
    started = request(args.base_url, "/api/performance/start", "POST")
    if not started.get("running") or not started.get("config_locked"):
        raise RuntimeError("performance did not enter its locked running state")
    deadline = time.monotonic() + max(1.0, args.duration_seconds)
    try:
        while time.monotonic() < deadline:
            status = request(args.base_url, "/api/runtime/status")
            if not status.get("running"):
                failures.append("runtime stopped unexpectedly")
                break
            metrics = status.get("performance_metrics", {})
            scheduler = metrics.get("scheduler_jitter_p95_ms")
            transcription = metrics.get("transcription_to_midi_p95_ms")
            model_ms = status.get("magenta", {}).get("health", {}).get("average_model_ms")
            if scheduler is not None and scheduler > 20:
                failures.append(f"scheduler jitter p95 exceeded 20ms: {scheduler}")
            if transcription is not None and transcription > 450:
                failures.append(f"transcription-to-MIDI p95 exceeded 450ms: {transcription}")
            if model_ms is not None and model_ms > 40:
                failures.append(f"MRT2 average frame exceeded 40ms: {model_ms}")
            output = status.get("outputs", {})
            print(json.dumps({
                "elapsed_seconds": round(args.duration_seconds - max(0.0, deadline - time.monotonic()), 1),
                "section": status.get("form", {}).get("section_id"),
                "fallbacks": status.get("fallback_count"),
                "magenta": status.get("magenta", {}).get("detail"),
                "scheduler_p95_ms": scheduler,
                "transcription_p95_ms": transcription,
                "output_errors": output.get("errors"),
            }, ensure_ascii=False))
            if failures:
                break
            time.sleep(max(0.5, args.poll_seconds))
    finally:
        request(args.base_url, "/api/performance/stop", "POST")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: adaptive performance soak completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
