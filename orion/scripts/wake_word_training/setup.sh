#!/usr/bin/env bash
# One-time setup for the "Hey Orion" wake word training pipeline (see README.md
# in this directory). Creates a dedicated venv — kept separate from the
# assistant's own requirements.txt since this pulls in a heavy, one-off ML
# toolchain that has no business on a Pi doing normal assistant work.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
# Pinned rather than "latest": current torch/torchaudio (2.9+) moved audio
# loading onto torchcodec (a separate package needing real FFmpeg shared
# libraries, not just the CLI) and dropped the torchaudio.info/load API
# that torch_audiomentations (used by openwakeword's augment_clips) still
# expects — that combination breaks --augment_clips with either
# "Could not load libtorchcodec" or "module 'torchaudio' has no attribute
# 'info'". 2.3.1 predates that migration and Just Works.
./venv/bin/pip install --quiet "torch==2.3.1" "torchaudio==2.3.1" "numpy<2" "scipy==1.13.1"
./venv/bin/pip install --quiet \
    torchinfo torchmetrics onnx onnxruntime \
    audiomentations torch-audiomentations speechbrain acoustics pronouncing mutagen webrtcvad \
    tqdm pyyaml openwakeword
./venv/bin/pip install --quiet piper-phonemize==1.1.0

# Upstream bug workaround (openwakeword 0.6.0, openwakeword/data.py):
# augment_clips()'s RIR-reverb branch does `rir_waveform, sr = torchaudio.load(...)`,
# shadowing the function's own `sr` parameter (the *audio* sample rate) with the
# *RIR file's* sample rate (44100 vs the expected 16000). Once RIR augmentation
# fires once (p=0.5 per batch), every later batch's sample-rate check compares
# against the wrong value and raises "Clip does not have the correct sample rate!"
# even though nothing is actually wrong with the clips. Renaming the loop-local
# variable fixes it without touching any public behavior.
sed -i \
    's/rir_waveform, sr = torchaudio.load(random.choice(RIR_paths))/rir_waveform, _rir_sr = torchaudio.load(random.choice(RIR_paths))/' \
    "$(./venv/bin/python -c 'import openwakeword.data, os; print(os.path.abspath(openwakeword.data.__file__))')"

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
# They're stereo, but openwakeword.data.augment_clips's RIR convolution
# (unlike its own apply_reverb helper, oddly) assumes mono and crashes
# ("only integer tensors of a single element can be converted to an index")
# on a stereo kernel — downmix in place to dodge that.
../../venv/bin/python -c "
import torchaudio
from pathlib import Path
for f in sorted(Path('piper_sample_generator/impulses').glob('*.wav')):
    w, sr = torchaudio.load(str(f))
    torchaudio.save(str(f), w.mean(dim=0, keepdim=True), sr)
"
cd ..

# openWakeWord's frozen feature-extraction models (melspectrogram + embedding)
# and its bundled VAD model — hosted on a GitHub release, not HuggingFace.
./venv/bin/python -c "from openwakeword.utils import download_models; download_models(model_names=['__none__'])"

echo "Setup complete. Next: ./venv/bin/python download_speech_commands.py --output-dir <path>"
