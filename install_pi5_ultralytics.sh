#!/bin/bash
set -e

echo "=== Sana Raspberry Pi 5 YOLO/OCR Install ==="

echo "[1/6] Updating OS packages..."
sudo apt update
sudo apt install -y \
  python3-pip \
  python3-venv \
  python3-dev \
  python3-opencv \
  python3-numpy \
  libopenblas0 \
  rpicam-apps \
  mpg123 \
  espeak \
  ffmpeg \
  git

echo "[2/6] Removing old virtual environment..."
rm -rf ~/sana_venv

echo "[3/6] Creating virtual environment with system packages..."
python3 -m venv ~/sana_venv --system-site-packages
source ~/sana_venv/bin/activate

echo "[4/6] Upgrading pip tools..."
pip install --upgrade pip setuptools wheel

echo "[5/6] Installing Python packages..."
pip install --no-cache-dir requests pyserial deep-translator gTTS pillow pyyaml

echo "[6/6] Installing Ultralytics..."
pip install --no-cache-dir ultralytics

echo "=== Install completed ==="
echo "Test imports with:"
echo "source ~/sana_venv/bin/activate"
echo "python3 -c \"import torch, cv2; from ultralytics import YOLO; print('OK')\""
