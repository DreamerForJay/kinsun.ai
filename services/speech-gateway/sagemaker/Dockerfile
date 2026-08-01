# BYOC image for the nan-TW/hak-TW SageMaker endpoint(s). See
# ../docs/sagemaker-endpoint-contract.md for the full deployment steps and
# ../docs/model-selection.md for why these specific models were chosen.
#
# One image serves both ASR and TTS -- set SAGEMAKER_INFERENCE_MODE=asr|tts
# as a container environment variable per SageMaker Model at deploy time
# (see ./serve), rather than building two images.
#
# Two Python environments, mirroring the PoC repo's local
# .venv310/.venv-voxhakka split: coqui-tts (needed for VoxHakka, the hak TTS
# provider) pins an older transformers API than Taiwan-Tongues ASR/MMS-TTS
# need, so they cannot share one venv. inference_tts.py calls into the
# voxhakka venv via subprocess (scripts/voxhakka_synthesize.py), exactly
# like VoxHakkaAdapter already does on a local machine -- this container
# relocates that existing solution, it does not solve the problem again.
#
# NEVER PUSHED TO ECR OR DEPLOYED on the machine this was written on (no AWS
# credentials available there) -- `docker build` was used to confirm the
# Dockerfile is valid and both venvs' dependencies resolve, nothing more.
# torch is unpinned (see requirements-asr.txt) pending an instance-type
# decision -- pin it before a real build.

FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      build-essential \
      git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/program

# --- Main venv: ASR (Taiwan-Tongues) + nan TTS (MMS-TTS) ---
COPY requirements-asr.txt .
RUN python -m venv /opt/program/.venv-main \
    && /opt/program/.venv-main/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/program/.venv-main/bin/pip install --no-cache-dir -r requirements-asr.txt

# --- Isolated venv: hak TTS (VoxHakka / coqui-tts) ---
COPY requirements-voxhakka.txt .
RUN python -m venv /opt/program/.venv-voxhakka \
    && /opt/program/.venv-voxhakka/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/program/.venv-voxhakka/bin/pip install --no-cache-dir -r requirements-voxhakka.txt

COPY core/ ./core/
COPY scripts/ ./scripts/
COPY inference_asr.py inference_tts.py serve ./
RUN chmod +x ./serve

ENV SAGEMAKER_INFERENCE_MODE=asr
EXPOSE 8080
ENTRYPOINT ["/opt/program/.venv-main/bin/python", "/opt/program/serve"]
