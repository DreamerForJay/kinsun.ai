#!/usr/bin/env python3
"""Standalone VoxHakka (Hakka TTS) CLI, run under .venv-voxhakka.

Isolated in its own venv/process because coqui-tts needs an older
transformers API than the rest of the project (Taiwan-Tongues ASR, MMS-TTS)
uses, so it can't share local_poc's main .venv310. See speech_adapters.py's
VoxHakkaAdapter, which shells out to this script as a subprocess.

Adapted from the official model card usage example at
https://huggingface.co/formospeech/yourtts-htia-240704 -- the Space that
originally hosted this code (with a VitsConfig compatibility patch) is no
longer published, so the patch below is reconstructed rather than copied:
the current coqui-tts declares CharactersConfig.characters as `str`, this
checkpoint's config.json stores it as a JSON array, coqpit silently drops
the mismatched field to None, and the model then builds a wrong-sized
default vocab (67 symbols instead of the checkpoint's 63) and fails to
load its state_dict. Confirmed fixed by widening the field type back to
list (see _PatchedCharactersConfig below) -- verified end-to-end with a
real synthesis call, not just "imports without erroring".

Must run with PYTHONUTF8=1 -- formog2p's own JSON data loader doesn't pass
encoding="utf-8" to open(), so on Windows it defaults to the cp950 codepage
and crashes on the (UTF-8) data file otherwise.
"""
import argparse
import json
import os
import re

from dataclasses import dataclass

import numpy as np
import torch
from huggingface_hub import snapshot_download
from scipy.io.wavfile import write as write_wav
from TTS.tts.configs.shared_configs import CharactersConfig
from TTS.tts.configs.vits_config import VitsConfig
import TTS.tts.configs.vits_config as vits_config_module

# The current coqui-tts release declares CharactersConfig.characters as a
# bare `str`, but this checkpoint's config.json stores it as a JSON array of
# vocab symbols (individual IPA glyphs and multi-digit tone numbers like
# "113" that must NOT be re-split by char). Coqpit's deserializer silently
# rejects the type mismatch and falls back to characters=None, which builds
# a wrong-sized (67 vs the checkpoint's 63) default vocab and breaks
# state_dict loading. This is what the official Space's (no longer
# published) "ChangedVitsConfig" patch existed to fix -- widen the field
# type back to list so the real vocab survives deserialization.
@dataclass
class _PatchedCharactersConfig(CharactersConfig):
    characters: list = None


@dataclass
class _PatchedVitsConfig(VitsConfig):
    characters: _PatchedCharactersConfig = None


vits_config_module.VitsConfig = _PatchedVitsConfig

from TTS.utils.synthesizer import Synthesizer  # noqa: E402  (after the patch)

MODEL_ID = "formospeech/yourtts-htia-240704"

# Model card dialect name -> formog2p dialect code.
DIALECTS = {
    "sixian": "hak_sx",
    "hailu": "hak_hl",
    "dapu": "hak_dp",
    "raoping": "hak_rp",
    "zhaoan": "hak_za",
    "nansixian": "hak_nsx",
}


def parse_ipa(ipa: str, delete_chars=r"\+\-\|\_", as_space: str = "") -> list[str]:
    text = []
    ipa_list = re.split(r"(?<![\d])(?=[\d])|(?<=[\d])(?![\d])", ipa)
    for word in ipa_list:
        if word.isdigit():
            text.append(word)
        else:
            if len(as_space) > 0:
                word = re.sub(r"[{}]".format(as_space), " ", word)
            if len(delete_chars) > 0:
                word = re.sub(r"[{}]".format(delete_chars), "", word)
            word = word.replace("，", " ， ")
            text.extend(word)
    return text


def load_model(model_id: str = MODEL_ID) -> Synthesizer:
    model_dir = snapshot_download(model_id)
    config_file_path = os.path.join(model_dir, "config.json")
    model_ckpt_path = os.path.join(model_dir, "model.pth")
    speaker_file_path = os.path.join(model_dir, "speakers.pth")
    language_file_path = os.path.join(model_dir, "language_ids.json")
    speaker_embedding_file_path = os.path.join(model_dir, "speaker_embs.pth")

    temp_config_path = os.path.join(model_dir, "_resolved_config.json")
    with open(config_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    # JSON has no meaning for a bare backslash; Windows paths need forward
    # slashes (which every consumer here -- json, TTS, torch -- accepts
    # fine) or they'd need escaping to \\ instead.
    content = content.replace("speakers.pth", speaker_file_path.replace("\\", "/"))
    content = content.replace("language_ids.json", language_file_path.replace("\\", "/"))
    content = content.replace(
        "speaker_embs.pth", speaker_embedding_file_path.replace("\\", "/")
    )
    with open(temp_config_path, "w", encoding="utf-8") as f:
        f.write(content)

    return Synthesizer(
        tts_checkpoint=model_ckpt_path,
        tts_config_path=temp_config_path,
        use_cuda=torch.cuda.is_available(),
    )


def synthesize(
    text: str, dialect: str, speaker: str, output_path: str, speed: float = 1.0,
) -> dict:
    from formog2p.hakka import g2p

    if dialect not in DIALECTS:
        raise ValueError(f"Unknown dialect '{dialect}'. Choices: {list(DIALECTS)}")

    model = load_model()
    result = g2p(text, DIALECTS[dialect], include_eng=True)
    if result.unknown_words:
        raise ValueError(
            f"Words could not be converted to IPA: {', '.join(result.unknown_words)}"
        )

    parsed_ipa = [p.replace(" ", "|") for p in result.pronunciations]
    parsed_ipa = parse_ipa(" ".join(parsed_ipa))

    model.tts_model.length_scale = speed
    wav = model.tts(
        parsed_ipa, speaker_name=speaker, language_name=dialect, split_sentences=False,
    )
    sample_rate = model.tts_model.config.audio.sample_rate
    wav = np.asarray(wav, dtype=np.float32)
    write_wav(output_path, sample_rate, wav)
    return {"output_path": output_path, "sample_rate": sample_rate, "dialect": dialect}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--dialect", default="sixian", choices=list(DIALECTS))
    parser.add_argument("--speaker", default="XF")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    info = synthesize(args.text, args.dialect, args.speaker, args.out, args.speed)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
