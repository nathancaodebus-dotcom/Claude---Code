#!/usr/bin/env bash
# One-time setup for the "Hey Orion" wake word training pipeline (see README.md
# in this directory). Creates a dedicated venv — kept separate from the
# assistant's own requirements.txt since this pulls in a heavy, one-off ML
# toolchain that has no business on a Pi doing normal assistant work.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet torch torchaudio "numpy<2" "scipy==1.13.1"
./venv/bin/pip install --quiet \
    torchinfo torchmetrics onnx onnxruntime \
    audiomentations torch-audiomentations speechbrain acoustics pronouncing mutagen webrtcvad \
    tqdm pyyaml openwakeword
./venv/bin/pip install --quiet piper-phonemize==1.1.0

if [ ! -d piper-sample-generator ]; then
    git clone https://github.com/rhasspy/piper-sample-generator
fi
cd piper-sample-generator
git checkout v2.0.0
mkdir -p models
if [ ! -f models/en_US-libritts_r-medium.pt ]; then
    curl -sSL -o models/en_US-libritts_r-medium.pt \
        "https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt"
fi
# PyTorch 2.6+ changed torch.load's default to weights_only=True, which
# breaks loading this checkpoint (a full pickled model object). The
# checkpoint is from the official GitHub release, so this is safe.
sed -i 's/model = torch.load(model_path)/model = torch.load(model_path, weights_only=False)/' generate_samples.py
# Bundled real (if small) room impulse responses, only present on a later
# branch than the v2.0.0 tag this script otherwise pins to.
git checkout origin/master -- piper_sample_generator/impulses
cd ..

# openWakeWord's frozen feature-extraction models (melspectrogram + embedding)
# and its bundled VAD model — hosted on a GitHub release, not HuggingFace.
./venv/bin/python -c "from openwakeword.utils import download_models; download_models(model_names=['__none__'])"

echo "Setup complete. Next: ./venv/bin/python download_speech_commands.py --output-dir <path>"
