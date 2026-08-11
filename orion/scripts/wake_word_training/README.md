# Training the "Hey Orion" wake word model

This directory holds the pipeline that produced `wake_word_models/hey_orion.onnx`
— the custom openWakeWord model that lets you actually say "Hey Orion" on the
Pi, since openWakeWord ships no pretrained model for that phrase (its bundled
models are alexa, hey_mycroft, hey_jarvis, timer, weather).

## Why this isn't the official openWakeWord recipe

openWakeWord's own [automatic training notebook](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb)
leans on Hugging Face for almost everything: the large negative training
corpus (2,000 hours from ACAV100M), the false-positive validation set, room
impulse responses (MIT's dataset), and background noise (AudioSet). The
environment this model was trained in blocks Hugging Face by network policy,
so this pipeline substitutes:

| Official source (blocked here) | Substitute used here |
|---|---|
| ACAV100M precomputed negative features (HF) | [Google Speech Commands v0.02](https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz) (~105k real word clips across 35 classes, GCS-hosted), run through openWakeWord's own feature extractor |
| ~11h HF-hosted false-positive validation set | A 5% held-out split of the same Speech Commands clips |
| MIT room impulse responses (HF) | The 8 impulse responses bundled directly in the `piper-sample-generator` git repo |
| AudioSet / FMA background noise (HF) | Google Speech Commands' own `_background_noise_` folder (6 ambient recordings) |
| Multi-speaker TTS checkpoint for positives | Unaffected — `piper-sample-generator`'s LibriTTS-R checkpoint is hosted on a GitHub release, not HF, so this part *is* the official method |

**Honest limitation**: Speech Commands is real audio but far smaller and
less varied than the official 2,000-hour set, so this baseline model likely
has a higher false-accept/false-reject rate than a model trained the
official way. The single biggest thing you can do to improve it is add real
recordings of yourself (and anyone else who'll use it) saying "Hey Orion" —
see "Improving the model" below.

## Reproducing or retraining

Everything here runs in its own venv, kept separate from the assistant's
runtime dependencies (`requirements.txt`) since this pulls in a heavy,
one-off ML toolchain (torch, speechbrain, audiomentations...) that has no
business on a Pi doing normal assistant work.

```bash
./setup.sh                          # creates ./venv, clones piper-sample-generator, downloads checkpoint + feature models
./venv/bin/python download_speech_commands.py --output-dir /path/to/data   # ~2.4GB
./venv/bin/python build_negative_features.py --speech-commands-dir /path/to/data/speech_commands_extracted --output-dir /path/to/data/features
# edit hey_orion.yaml: point piper_sample_generator_path / background_paths / feature_data_files / false_positive_validation_data_path at your paths
./venv/bin/python -m openwakeword.train --training_config hey_orion.yaml --generate_clips
./venv/bin/python -m openwakeword.train --training_config hey_orion.yaml --augment_clips
./venv/bin/python -m openwakeword.train --training_config hey_orion.yaml --train_model
cp /path/to/output/hey_orion/hey_orion.onnx ../../wake_word_models/hey_orion.onnx
```

Ran end-to-end on 4 CPU cores (no GPU) in a few hours; the negative feature
extraction step (converting ~100k Speech Commands clips to openWakeWord's
embedding format) is the single longest step.

## Improving the model with real recordings

Synthetic TTS, however diverse, doesn't fully match a real voice in a real
room. To sharpen this model:

1. Record yourself saying "Hey Orion" ~20-30 times (varying distance,
   tone, background noise) — easiest way is sending them as Telegram voice
   notes to Orion, since that pipeline already exists.
2. Drop the resulting `.wav` files (converted to 16kHz mono — `ffmpeg -i in.ogg -ar 16000 -ac 1 out.wav`)
   into `<output_dir>/hey_orion/positive_train/` alongside the synthetic
   ones before the `--augment_clips` step, so they get mixed into training
   with the same augmentation (noise, reverb) as everything else.
3. A few recordings of things that sound similar but *aren't* the wake
   word (other names, "hey" alone) into `negative_train/` as hard negatives
   helps too.
4. Re-run `--augment_clips` and `--train_model`, then swap the new
   `hey_orion.onnx` into `wake_word_models/`.

## Files

- `hey_orion.yaml` — training config (paths need adjusting to wherever you put the data — see above)
- `build_negative_features.py` — converts raw Speech Commands audio into openWakeWord's precomputed feature format
- `download_speech_commands.py` — fetches and extracts the substitute negative dataset
- `piper-sample-generator/` — not committed (see `.gitignore`); `setup.sh` clones it fresh
