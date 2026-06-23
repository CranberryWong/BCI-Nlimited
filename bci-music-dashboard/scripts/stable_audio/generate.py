from __future__ import annotations

import argparse
from pathlib import Path
import time

import soundfile as sf
import torch
from diffusers import StableAudioPipeline
from huggingface_hub.errors import GatedRepoError


MODEL_ID = "stabilityai/stable-audio-open-1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a short WAV with Stable Audio Open.")
    parser.add_argument(
        "--prompt",
        default=(
            "soft Chinese wooden percussion, sparse ambient texture, "
            "calm, instrumental, no vocals"
        ),
    )
    parser.add_argument(
        "--negative-prompt",
        default="vocals, speech, distortion, harsh noise, clipping",
    )
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance-scale", type=float, default=7.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    parser.add_argument("--output", default="generated_audio/stable-audio-test.wav")
    return parser.parse_args()


def resolve_device(requested: str) -> str:
    if requested == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if requested == "mps" and not torch.backends.mps.is_available():
        raise SystemExit("MPS is unavailable in this PyTorch environment; use --device cpu.")
    return requested


def main() -> int:
    args = parse_args()
    if not 1 <= args.seconds <= 47:
        raise SystemExit("--seconds must be between 1 and 47")
    if not 1 <= args.steps <= 200:
        raise SystemExit("--steps must be between 1 and 200")

    device = resolve_device(args.device)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Loading {MODEL_ID} on {device}...")
    started = time.perf_counter()

    try:
        pipe = StableAudioPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    except GatedRepoError as exc:
        raise SystemExit(
            "\nStable Audio Open is a gated model. The current Hugging Face account "
            "has not been granted access.\n"
            "1. Open https://huggingface.co/stabilityai/stable-audio-open-1.0\n"
            "2. Sign in with the same account used by `hf auth whoami`.\n"
            "3. Accept the license and click Agree/Request access.\n"
            "4. After access is granted, run this command again.\n"
            "The existing read token normally does not need to be recreated."
        ) from exc
    pipe = pipe.to(device)
    pipe.enable_attention_slicing()
    generator = torch.Generator(device="cpu").manual_seed(args.seed)

    result = pipe(
        args.prompt,
        negative_prompt=args.negative_prompt,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance_scale,
        audio_end_in_s=args.seconds,
        num_waveforms_per_prompt=1,
        generator=generator,
    )
    audio = result.audios[0].detach().cpu().float().numpy().T
    sf.write(output, audio, pipe.vae.sampling_rate, subtype="PCM_16")
    elapsed = time.perf_counter() - started
    print(f"Saved {args.seconds:.1f}s audio to {output}")
    print(f"Elapsed: {elapsed:.1f}s; device={device}; steps={args.steps}; seed={args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
