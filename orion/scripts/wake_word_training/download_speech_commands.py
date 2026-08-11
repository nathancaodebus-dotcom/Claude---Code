"""Downloads and extracts Google Speech Commands v0.02 — the substitute
negative/background dataset used by this pipeline in place of the official
(Hugging Face-hosted, blocked in the environment this was built in) AudioSet
and ACAV100M sources. See README.md in this directory for why.

~2.4GB download, ~3.3GB extracted (105k short word clips + ambient noise).
"""
from __future__ import annotations

import argparse
import tarfile
from pathlib import Path

import httpx

_URL = "https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / "speech_commands_v0.02.tar.gz"
    extract_dir = output_dir / "speech_commands_extracted"

    if not archive_path.exists():
        print(f"Downloading {_URL} -> {archive_path}")
        with httpx.stream("GET", _URL, timeout=600, follow_redirects=True) as response:
            response.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
    else:
        print(f"Already downloaded: {archive_path}")

    if not extract_dir.exists():
        print(f"Extracting -> {extract_dir}")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path) as tar:
            tar.extractall(extract_dir)
    else:
        print(f"Already extracted: {extract_dir}")

    print(f"Done. Negative audio ready at: {extract_dir}")


if __name__ == "__main__":
    main()
