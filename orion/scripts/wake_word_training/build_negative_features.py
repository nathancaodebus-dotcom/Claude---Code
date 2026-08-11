"""One-off step: convert Google Speech Commands (raw negative audio — words
that are definitely not "hey orion", plus ambient background noise) into
openWakeWord's precomputed feature format, standing in for the official
HuggingFace-hosted ACAV100M negative feature set that this environment
can't reach (see README in this directory for why).

Usage: python build_negative_features.py --speech-commands-dir /path/to/speech_commands_extracted \
    --output-dir /path/to/output
"""
from __future__ import annotations

import argparse
import random
import wave
from pathlib import Path

import numpy as np
import torch

CLIP_SAMPLES = 32000  # 2 seconds at 16kHz, matches openwakeword.data's default stack_clips size
SAMPLE_RATE = 16000


def _load_wav_as_tensor(path: Path) -> torch.Tensor:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    return torch.from_numpy(audio)


def _batch_generator(paths: list[Path], batch_size: int):
    from openwakeword.data import create_fixed_size_clip

    for i in range(0, len(paths), batch_size):
        batch_paths = paths[i : i + batch_size]
        clips = [create_fixed_size_clip(_load_wav_as_tensor(p), CLIP_SAMPLES) for p in batch_paths]
        yield np.stack(clips).astype(np.int16)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speech-commands-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--val-fraction", type=float, default=0.05)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    from openwakeword.utils import compute_features_from_generator

    sc_dir = Path(args.speech_commands_dir)
    word_dirs = [
        d for d in sc_dir.iterdir() if d.is_dir() and d.name not in ("_background_noise_",)
    ]
    all_clips = sorted(p for d in word_dirs for p in d.glob("*.wav"))
    print(f"Found {len(all_clips)} negative word clips across {len(word_dirs)} classes")

    rng = random.Random(args.seed)
    rng.shuffle(all_clips)
    n_val = int(len(all_clips) * args.val_fraction)
    val_clips, train_clips = all_clips[:n_val], all_clips[n_val:]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for split_name, clips in (("train", train_clips), ("val", val_clips)):
        out_path = output_dir / f"speech_commands_features_{split_name}.npy"
        print(f"Computing {split_name} features for {len(clips)} clips -> {out_path}")
        compute_features_from_generator(
            _batch_generator(clips, args.batch_size),
            n_total=len(clips),
            clip_duration=CLIP_SAMPLES,
            output_file=str(out_path),
        )
        print(f"Done: {out_path}")

    # openwakeword's false-positive validation loader (train.py) expects a
    # flat (total_frames, 96) stream to window over — not the (n_clips, 16, 96)
    # shape used everywhere else — because the *official* validation set is
    # one long continuous recording. Ours is many independent clips, so we
    # approximate that by concatenating them frame-by-frame; a handful of
    # windows will span a clip boundary, which is a minor, acceptable
    # artifact for a validation-only signal.
    val_path = output_dir / "speech_commands_features_val.npy"
    val_clips_arr = np.load(val_path)
    np.save(output_dir / "speech_commands_features_val_flat.npy", val_clips_arr.reshape(-1, val_clips_arr.shape[-1]))
    print(f"Wrote flattened false-positive validation stream: {output_dir / 'speech_commands_features_val_flat.npy'}")


if __name__ == "__main__":
    main()
