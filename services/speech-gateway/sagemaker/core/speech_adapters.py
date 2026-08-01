"""ASR/TTS adapters.

Heavy SDKs and model libraries are imported lazily. This keeps evaluation and
mock regression runnable on a machine without AWS credentials or model weights.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import types
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from speech_contracts import ASRResult, SessionContext, TTSResult
from speech_normalization import (
    extract_entities,
    normalize_text,
    requires_confirmation,
    to_tailo,
)


def audio_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except (wave.Error, OSError, ZeroDivisionError):
        return None


class ASRAdapter(ABC):
    provider = "unknown"
    model_id = "unknown"
    model_version = "unknown"

    @abstractmethod
    def transcribe(
        self, audio: Path, requested_language: str, context: SessionContext
    ) -> ASRResult:
        raise NotImplementedError


class TTSAdapter(ABC):
    provider = "unknown"
    model_id = "unknown"

    @abstractmethod
    def synthesize(
        self, text: str, language: str, voice: str, speed: float, output: Path
    ) -> TTSResult:
        raise NotImplementedError


class MockASRAdapter(ASRAdapter):
    provider = "mock"
    model_id = "fixture-transcript"
    model_version = "1"

    def transcribe(
        self, audio: Path, requested_language: str, context: SessionContext
    ) -> ASRResult:
        started = time.perf_counter()
        transcript_path = audio.with_suffix(".txt")
        transcript = transcript_path.read_text(encoding="utf-8").strip()
        duration = audio_duration_seconds(audio)
        latency = (time.perf_counter() - started) * 1000
        confidence = 0.99
        return ASRResult(
            transcript=transcript,
            normalized_transcript=normalize_text(transcript, requested_language),
            detected_language=requested_language,
            confidence=confidence,
            key_entities=extract_entities(transcript, context.key_entities),
            provider=self.provider,
            model_id=self.model_id,
            model_version=self.model_version,
            latency_ms=latency,
            realtime_factor=(latency / 1000 / duration) if duration else None,
            needs_confirmation=requires_confirmation(
                transcript, confidence, context.key_entities
            ),
        )


class TransformersASRAdapter(ASRAdapter):
    provider = "huggingface-transformers"

    def __init__(
        self, model_id: str, device: int = -1,
        language_code: str | dict[str, str] | None = None,
        chunk_length_s: float | None = 30,
    ):
        self.model_id = model_id
        self.model_version = "pinned-by-model-id"
        self.device = device
        # str/None: same generation hint for every call (existing behavior).
        # dict: per-requested_language hint, so one loaded model can serve
        # several languages without a separate pipeline (and separate VRAM
        # allocation) per language -- e.g. voice_server.py shares one
        # Taiwan-Tongues pipeline across en/hak/nan/mixed-zh-nan, where
        # en needs "english" but the others need "chinese" (no dedicated
        # hak/nan token exists in any release format of this model).
        self.language_code = language_code
        # chunk_length_s>0 forces transformers' chunked long-form decoding
        # path even for short single-utterance audio; pass None/0 to use
        # plain short-form generate() instead, matching a bare model-card
        # example. NOTE: tested as a fix for Breeze-ASR-26's runaway
        # generation (2026-08-01) -- it did NOT help, CER got worse (466%)
        # and latency roughly doubled (mean 59s, max 220s vs. chunked
        # 20-40s/142s p95). Root cause is still open; kept configurable
        # since it's a legitimate general knob, not because it fixed Breeze.
        self.chunk_length_s = chunk_length_s
        self._pipeline: Any = None

    def _load(self) -> Any:
        if self._pipeline is None:
            from transformers import pipeline
            pipeline_kwargs = {}
            if self.chunk_length_s:
                pipeline_kwargs["chunk_length_s"] = self.chunk_length_s
            self._pipeline = pipeline(
                "automatic-speech-recognition",
                model=self.model_id,
                device=self.device,
                **pipeline_kwargs,
            )
        return self._pipeline

    def transcribe(
        self, audio: Path, requested_language: str, context: SessionContext
    ) -> ASRResult:
        started = time.perf_counter()
        kwargs = {}
        # None -> use requested_language (default); "" -> explicitly no hint,
        # for checkpoints (e.g. Breeze-ASR-26) whose own fine-tuning already
        # bakes in fixed decoder behavior and misbehaves if generate_kwargs
        # forces a language/task on top of it; dict -> per-language hint,
        # missing key falls back to "" (no hint) rather than crashing.
        if isinstance(self.language_code, dict):
            language = self.language_code.get(requested_language, "")
        elif self.language_code is None:
            language = requested_language
        else:
            language = self.language_code
        if language:
            kwargs["generate_kwargs"] = {"language": language, "task": "transcribe"}
        raw = self._load()(str(audio), **kwargs)
        transcript = raw["text"].strip()
        latency = (time.perf_counter() - started) * 1000
        duration = audio_duration_seconds(audio)
        return ASRResult(
            transcript=transcript,
            normalized_transcript=normalize_text(transcript, requested_language),
            detected_language=requested_language,
            confidence=None,
            key_entities=extract_entities(transcript, context.key_entities),
            provider=self.provider,
            model_id=self.model_id,
            model_version=self.model_version,
            latency_ms=latency,
            realtime_factor=(latency / 1000 / duration) if duration else None,
            needs_confirmation=requires_confirmation(
                transcript, None, context.key_entities
            ),
        )


class CTranslate2ASRAdapter(ASRAdapter):
    provider = "faster-whisper"

    def __init__(
        self,
        model_id: str,
        device: str = "cpu",
        compute_type: str = "int8",
        model_version: str = "pinned-by-model-id",
    ):
        self.model_id = model_id
        # 部署時傳入不可變 revision，讓 trace 能指出實際執行的模型版本。
        self.model_version = model_version
        self.device = device
        self.compute_type = compute_type
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            # Some managed Windows environments block PyAV's native DLLs.
            # We pass decoded NumPy audio to faster-whisper, so a minimal
            # import stub is sufficient at *import time* and does not
            # weaken the OS application policy -- but it must not leak into
            # sys.modules afterward: a real `import av` elsewhere in the
            # same process (transformers' own audio pipeline, used by
            # TransformersASRAdapter, probes for it) would otherwise pick up
            # this fake module instead of doing a real import and fail with
            # "av.__spec__ is None". Confirmed 2026-07-31: this only
            # surfaces once both adapter types are used in the same process
            # (e.g. voice_server.py routing zh through this adapter and
            # en/hak/nan through TransformersASRAdapter), which never
            # happened before per-language routing existed.
            stub_installed = os.name == "nt" and "av" not in sys.modules
            if stub_installed:
                sys.modules["av"] = types.ModuleType("av")
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(
                    self.model_id, device=self.device, compute_type=self.compute_type
                )
            finally:
                if stub_installed:
                    del sys.modules["av"]
        return self._model

    def transcribe(
        self, audio: Path, requested_language: str, context: SessionContext
    ) -> ASRResult:
        started = time.perf_counter()
        import numpy as np
        import soundfile as sf
        waveform, sample_rate = sf.read(str(audio), dtype="float32")
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)
        if sample_rate != 16000:
            target_length = round(len(waveform) * 16000 / sample_rate)
            source_positions = np.linspace(0.0, 1.0, len(waveform), endpoint=False)
            target_positions = np.linspace(0.0, 1.0, target_length, endpoint=False)
            waveform = np.interp(target_positions, source_positions, waveform).astype(
                np.float32
            )
        # The released CT2 tokenizer contains the standard Whisper <|zh|>
        # token but no <|nan|>/<|hak|> tokens, despite the model card listing
        # those locale codes. Use the shared Chinese decoder token while
        # retaining the requested locale in our provider-neutral result.
        inference_language = (
            "zh" if requested_language in {"nan", "hak", "mixed-zh-nan"}
            else requested_language
        )
        segments, info = self._load().transcribe(
            waveform, language=inference_language, vad_filter=True
        )
        segments = list(segments)
        transcript = "".join(segment.text for segment in segments).strip()
        latency = (time.perf_counter() - started) * 1000
        duration = audio_duration_seconds(audio)
        # `info.language_probability` only answers "which language is this?"
        # and must not be presented as transcript confidence. Use the
        # segment decoding log-probabilities as an explicit proxy instead.
        scored_segments = [
            segment for segment in segments
            if getattr(segment, "avg_logprob", None) is not None
        ]
        if scored_segments:
            weights = [
                max(0.01, float(segment.end) - float(segment.start))
                for segment in scored_segments
            ]
            confidence = sum(
                math.exp(min(0.0, float(segment.avg_logprob))) * weight
                for segment, weight in zip(scored_segments, weights)
            ) / sum(weights)
            confidence = max(0.0, min(1.0, confidence))
        else:
            confidence = None
        return ASRResult(
            transcript=transcript,
            normalized_transcript=normalize_text(transcript, requested_language),
            detected_language=requested_language,
            confidence=confidence,
            key_entities=extract_entities(transcript, context.key_entities),
            provider=self.provider,
            model_id=self.model_id,
            model_version=self.model_version,
            latency_ms=latency,
            realtime_factor=(latency / 1000 / duration) if duration else None,
            needs_confirmation=requires_confirmation(
                transcript, confidence, context.key_entities
            ),
        )


class AmazonPollyAdapter(TTSAdapter):
    provider = "amazon-polly"
    model_id = "polly-neural"

    LANGUAGE_VOICES = {"zh": ("cmn-CN", "Zhiyu"), "en": ("en-US", "Joanna")}

    def __init__(self, region: str):
        self.region = region

    def synthesize(
        self, text: str, language: str, voice: str, speed: float, output: Path
    ) -> TTSResult:
        if language not in self.LANGUAGE_VOICES:
            return TextFallbackTTS().synthesize(text, language, voice, speed, output)
        import boto3
        language_code, default_voice = self.LANGUAGE_VOICES[language]
        started = time.perf_counter()
        response = boto3.client("polly", region_name=self.region).synthesize_speech(
            Text=(
                f'<speak><prosody rate="{max(60, min(110, int(speed * 100)))}%">'
                f"{text}</prosody></speak>"
            ),
            TextType="ssml",
            OutputFormat="mp3",
            LanguageCode=language_code,
            VoiceId=voice or default_voice,
            Engine="neural",
        )
        payload = response["AudioStream"].read()
        first_ms = (time.perf_counter() - started) * 1000
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        total_ms = (time.perf_counter() - started) * 1000
        return TTSResult(
            str(output), self.provider, self.model_id, voice or default_voice,
            language, 24000, first_ms, total_ms, None, True,
        )


class MeloTTSAdapter(TTSAdapter):
    """myshell-ai/MeloTTS-Chinese: MIT, free, fully offline zh candidate.

    Mainland-accented Mandarin, not Taiwan-accented -- same limitation as
    Polly's Zhiyu voice. Only fills the "Polly has no credentials" gap for
    zh; it is not a Taiwan-accent quality claim. Requires the MeloTTS repo
    installed editable (`pip install -e .` from a clone of
    github.com/myshell-ai/MeloTTS) plus `python -m unidic download` --
    not a plain pip-installable package, so this fails loudly if missing
    rather than silently falling back.
    """

    provider = "melotts"
    model_id = "myshell-ai/MeloTTS-Chinese"

    def __init__(self):
        self._model: Any = None
        self._speaker_id: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from melo.api import TTS
            self._model = TTS(language="ZH", device="cuda")
            self._speaker_id = self._model.hps.data.spk2id["ZH"]
        return self._model

    def synthesize(
        self, text: str, language: str, voice: str, speed: float, output: Path
    ) -> TTSResult:
        if language != "zh":
            return TextFallbackTTS().synthesize(text, language, voice, speed, output)
        started = time.perf_counter()
        model = self._load()
        output = output.with_suffix(".wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        model.tts_to_file(text, self._speaker_id, str(output), speed=speed)
        first_ms = total_ms = (time.perf_counter() - started) * 1000
        return TTSResult(
            str(output), self.provider, self.model_id, "ZH-default",
            language, model.hps.data.sampling_rate, first_ms, total_ms, None, True,
        )


class VoxHakkaAdapter(TTSAdapter):
    """formospeech/yourtts-htia-240704 (VoxHakka): YourTTS-based, 6 Hakka
    dialects, CC-BY-NC-4.0.

    Runs as a subprocess against `.venv-voxhakka` (see
    `voxhakka_synthesize.py`), not the main venv310 -- coqui-tts pins an
    older transformers API that conflicts with the Taiwan-Tongues/MMS
    adapters' newer one. This is genuinely a better candidate than
    mms-tts-hak (dedicated multi-dialect model vs. one generic checkpoint),
    but like mms-tts-hak it hasn't cleared G2-G5 (no native-speaker quality
    review yet) -- explicit-choice only, never the "auto" default.
    """

    provider = "voxhakka"
    model_id = "formospeech/yourtts-htia-240704"

    DIALECTS = {"sixian", "hailu", "dapu", "raoping", "zhaoan", "nansixian"}

    def __init__(self, venv_python: Path | None = None, dialect: str = "sixian"):
        local_poc = Path(__file__).parent.parent  # this file lives in core/
        self.venv_python = venv_python or (
            local_poc / ".venv-voxhakka" / "Scripts" / "python.exe"
        )
        self.script = local_poc / "scripts" / "voxhakka_synthesize.py"
        self.dialect = dialect if dialect in self.DIALECTS else "sixian"

    def synthesize(
        self, text: str, language: str, voice: str, speed: float, output: Path
    ) -> TTSResult:
        if language != "hak":
            return TextFallbackTTS().synthesize(text, language, voice, speed, output)
        if not self.venv_python.exists():
            raise RuntimeError(
                f"VoxHakka venv not found at {self.venv_python}. See "
                "voxhakka_synthesize.py's module docstring for setup steps."
            )
        import subprocess

        dialect = voice if voice in self.DIALECTS else self.dialect
        output = output.with_suffix(".wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        env = dict(os.environ, PYTHONUTF8="1")
        proc = subprocess.run(
            [
                str(self.venv_python), str(self.script),
                "--text", text, "--dialect", dialect,
                "--speed", str(speed), "--out", str(output),
            ],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        total_ms = (time.perf_counter() - started) * 1000
        if proc.returncode != 0:
            raise RuntimeError(f"voxhakka_synthesize.py failed: {proc.stderr[-2000:]}")
        info = json.loads(proc.stdout.strip().splitlines()[-1])
        return TTSResult(
            str(output), self.provider, self.model_id, f"hak-{dialect}",
            language, info["sample_rate"], total_ms, total_ms, None, True,
        )


class MmsTTSAdapter(TTSAdapter):
    """Meta MMS (VITS) checkpoints, one per language.

    CC-BY-NC 4.0: fine for the hackathon demo, not for a commercial path.
    Fixed voice, no speed/emotion control, no zero-shot cloning. For nan/hak
    this answers "can this language produce live audio at all" per
    docs/SPEC.md's G0-G1 gates -- it has not cleared G2-G5, so the router
    must not treat it as the frozen Live Demo winner without a human
    decision (see docs/test_log.md).
    nan Han-character input is romanized to Tai-lo via taibun before
    synthesis (see speech_normalization.to_tailo); without that pass the
    tokenizer produced 0 ids and the model crashed, which is why this
    provider historically never emitted nan audio.
    For zh/en this is a fully offline fallback for when Polly credentials
    are not configured (see AmazonPollyAdapter), not a quality claim.
    """

    provider = "mms-tts"
    model_id = "facebook/mms-tts"

    # Meta never released a Mandarin/Chinese MMS-TTS checkpoint despite the
    # generic docs mentioning Mandarin as a uroman-preprocessing example --
    # confirmed by exhausting every plausible repo id (cmn, zho, chi, zh,
    # cmn-script_simplified/traditional) against the HF Hub API. Do not
    # re-add a "zh" entry here without first confirming a real repo id.
    LANGUAGE_MODELS = {
        "nan": "facebook/mms-tts-nan",
        "hak": "facebook/mms-tts-hak",
        "en": "facebook/mms-tts-eng",
    }

    def __init__(self):
        self._pipelines: dict[str, Any] = {}

    def _load(self, language: str) -> Any:
        if language not in self._pipelines:
            from transformers import pipeline
            self._pipelines[language] = pipeline(
                "text-to-speech", model=self.LANGUAGE_MODELS[language]
            )
        return self._pipelines[language]

    def synthesize(
        self, text: str, language: str, voice: str, speed: float, output: Path
    ) -> TTSResult:
        if language not in self.LANGUAGE_MODELS:
            return TextFallbackTTS().synthesize(text, language, voice, speed, output)
        import soundfile as sf
        started = time.perf_counter()
        # The nan/hak checkpoints' tokenizers only cover romanized text; Han
        # input tokenizes to 0 ids and crashes VitsModel.forward. taibun is
        # Hokkien-only, so only nan gets the Han->Tai-lo pass -- hak callers
        # should prefer VoxHakkaAdapter (own Han->IPA G2P) and may only reach
        # this adapter with already-romanized text.
        if language == "nan":
            text = to_tailo(text)
        synth = self._load(language)
        # transformers.VitsModel.forward accepts speaking_rate directly
        # (length_scale = 1.0/speaking_rate internally, so >1.0 is faster,
        # <1.0 slower) -- confirmed against installed transformers source
        # 2026-08-01. The pipeline's __call__ forwards unknown kwargs into
        # forward_params, so this actually reaches the model instead of
        # being silently dropped like a plain `speed=` kwarg would be.
        generated = synth(text, forward_params={"speaking_rate": speed})
        first_ms = (time.perf_counter() - started) * 1000
        output = output.with_suffix(".wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output, generated["audio"].squeeze(), generated["sampling_rate"])
        total_ms = (time.perf_counter() - started) * 1000
        return TTSResult(
            str(output), self.provider, self.LANGUAGE_MODELS[language],
            "mms-tts-default", language, generated["sampling_rate"],
            first_ms, total_ms, None, True,
        )


class TextFallbackTTS(TTSAdapter):
    provider = "text-fallback"
    model_id = "no-audio"

    def synthesize(
        self, text: str, language: str, voice: str, speed: float, output: Path
    ) -> TTSResult:
        output = output.with_suffix(".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"language": language, "text": text}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return TTSResult(
            str(output), self.provider, self.model_id, "text", language, 0,
            0.0, 0.0, None, False, "No validated TTS provider for this language",
        )
