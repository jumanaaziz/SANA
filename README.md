# <img src="https://img.shields.io/badge/SANA-Smart%20Assistive%20Navigation%20Aid-darkred?style=for-the-badge" />

<div align="center">

# SANA

### Smart Assistive Navigation Aid

AI-powered smart glasses for visually impaired navigation using Computer Vision, OCR, Voice Interaction, and Visual-Inertial Odometry.

</div>

---

## Overview

SANA is an intelligent wearable navigation system designed to help visually impaired individuals navigate safely and independently.

The system integrates:

* Computer Vision
* Obstacle Detection
* OCR & Sign Recognition
* Voice Interaction
* Haptic Feedback
* Indoor Localization

All powered by a Raspberry Pi 5 and AI models running on edge hardware.

---

# Features

* Real-time obstacle detection using YOLOv8
* OCR-based text & sign reading
* Speech-to-Text (STT)
* Text-to-Speech (TTS)
* Indoor localization 
* Haptic feedback using vibration motor
* Emergency contact calling
* Mobile application integration
* AI-powered navigation assistance
* Wearable smart glasses design

---

# System Architecture

```text
Camera + IMU + ToF Sensors
            ↓
      Raspberry Pi 5
            ↓
 AI Processing (YOLO/OCR)
            ↓
Decision & Navigation Engine
            ↓
 Audio Feedback + Vibration
            ↓
        User Guidance
```

---

# Hardware Components

| Component          | Purpose                 |
| ------------------ | ----------------------- |
| Raspberry Pi 5     | Main processing unit    |
| Camera Module      | Object & sign detection |
| BNO085 IMU         | Orientation tracking    |
| VL53L0X / VL53L1X  | Distance sensing        |
| MAX98357A          | Audio amplifier         |
| Microphone         | Voice commands          |
| Speaker / Earpiece | Audio output            |
| Touch Sensor       | User interaction        |
| Vibration Motor    | Haptic alerts           |
| Power Bank         | Portable power          |

---

# Software Stack

| Technology           | Usage              |
| -------------------- | ------------------ |
| Python               | Core development   |
| OpenCV               | Image processing   |
| YOLOv8               | Object detection   |
| OCR.space API        | OCR processing     |
| Whisper              | Speech recognition |
| FastAPI              | Backend services   |
| Firebase             | Cloud integration  |
| OpenVINS             | Localization       |
| Raspberry Pi OS      | Edge deployment    |

---

# AI Modules

## 1. Obstacle Detection

YOLOv8 detects:

* obstacles
* stairs
* doors
* Signs
* indoor objects

The system converts detections into real-time voice guidance.

---

## 2. OCR & Sign Reading

SANA:

1. Detects signs
2. Crops sign regions
3. Extracts text using OCR
4. Converts text into speech

Example:

```text
"Room 101 → Left"
```

---

# User Interaction

## Voice Commands

Users can:

* request destination
* ask for current location
* trigger emergency mode

---

## Haptic Feedback

Different vibration patterns indicate:

* Nearby obstacle
* Danger warning

---

# Emergency Feature

SANA supports emergency assistance by:

* calling saved emergency contacts
* sharing estimated user location

---

# Mobile Application

The companion application supports:

* authentication
* emergency contact management
* obstacle reporting
* cloud synchronization

---

# PCB & Wearable Design

The custom PCB integrates:

* IMU
* ToF sensor
* microphone
* touch sensor
* vibration motor
* audio amplifier

The Raspberry Pi 5 remains external/pocket-mounted to reduce heat and weight.

---

# Installation

## Clone Repository

```bash
git clone https://github.com/jumanaaziz/SANA.git
cd SANA
```

---

# Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Run Modules

## YOLO Detection

```bash
python yolo_detection.py
```

## OCR Module

```bash
python ocr_module.py
```

## Navigation System

```bash
python navigation.py
```

---

# Project Status

| Module                  | Status      |
| ----------------------- | ----------- |
| YOLO Integration        | Completed   |
| OCR Integration         | Completed   |
| TTS Integration         | Completed   |
| PCB Design              | Completed   |
| Raspberry Pi Deployment | Completed   |
| Sensor Integration      | Completed   |

---

# Future Improvements

* Fully embedded smart glasses PCB
* Offline OCR & STT
* SLAM-based mapping
* Bone-conduction audio
* Arabic AI voice assistant
* Lightweight battery optimization
* AI route planning

---

# Team

SANA Graduation Project Team
King Saud University — Software Engineering Department
Jumana Alwakeel, Jumana Alwzrah, Norah Alzahrani, Shaykhah Altamimi, Nouf Almandil
Subpervise by: Dr. Ohoud Alhrabi
special thanks to: KACST Team, Dr. Saleh Alhiji, and Ms. Hala Almukhlafi

---

# License

This project is intended for educational and research purposes.

---

<div align="center">

### SANA — Empowering Independent Navigation Through AI

</div>
