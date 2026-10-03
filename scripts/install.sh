#!/usr/bin/env bash
# install.sh — install agent-video-downloader (avd) and verify deps
set -euo pipefail

echo "[install] checking Python..."
python3 --version || { echo "[install] python3 missing"; exit 1; }

echo "[install] checking ffmpeg/ffprobe..."
if ! command -v ffprobe >/dev/null 2>&1; then
    echo "[install] ffprobe not found — installing ffmpeg..."
    sudo apt-get update -y && sudo apt-get install -y ffmpeg || {
        echo "[install] failed to install ffmpeg automatically"
        echo "[install] please install manually: sudo apt install ffmpeg"
        exit 1
    }
fi
ffprobe -version | head -1

echo "[install] pip install -e .[dev]..."
pip install -e .[dev]

echo "[install] verifying entry point..."
avd --version

echo "[install] OK"
