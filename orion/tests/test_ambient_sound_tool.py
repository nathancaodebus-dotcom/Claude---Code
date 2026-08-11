import wave

import pytest

from tools.ambient_sound_tool import GenerateAmbientSoundTool


@pytest.fixture(autouse=True)
def in_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("noise_type", ["white", "pink", "brown"])
def test_generates_valid_wav_file(noise_type):
    result = GenerateAmbientSoundTool().run(noise_type=noise_type, duration_seconds=1)
    assert noise_type in result

    path = f"outputs/{noise_type}_noise_1s.wav"
    with wave.open(path, "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 44100
        assert wav_file.getnframes() == 44100


def test_duration_is_capped():
    result = GenerateAmbientSoundTool().run(noise_type="white", duration_seconds=99999)
    assert "600s" in result
