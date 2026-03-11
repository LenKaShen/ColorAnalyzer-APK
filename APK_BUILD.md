# ColorAnalyzer Offline APK Build Guide

This project has been converted to an offline Kivy app for Android.

## What changed

- `main.py` is now the app entrypoint for Android packaging.
- `mobile_app.py` provides a local UI for:
  - Video mode: pick 3 videos (`control_min`, `control_max`, `sample`) + start time for each.
  - Image pair mode: pick start/end images for each role.
  - Start ROI and End ROI for each role (`x,y,w,h`).
  - Duration in `h:m:s`.
  - Optional calibration targets for control min/max.
- `core_analysis.py` runs CIELAB + CIEDE2000 math fully offline on-device.

## Build prerequisites

Buildozer packaging is Linux-first. On Windows, use WSL2 Ubuntu.

1. Install WSL2 + Ubuntu.
2. Open Ubuntu and install dependencies:

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv \
  autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
  libtinfo5 cmake libffi-dev libssl-dev
pip3 install --user --upgrade cython buildozer
```

## Build APK

From Ubuntu terminal:

```bash
cd /mnt/c/Users/millette/Downloads/updates/ColorAnalyzer/ColorAnalyzer/Decompiled
buildozer android debug
```

APK output will be in `bin/`.

## Install on phone

1. Enable USB debugging on Android.
2. Connect device.
3. Install APK:

```bash
adb install -r bin/*.apk
```

## Usage

- Open app on phone.
- Choose `Videos` or `Image Pairs`.
- Fill duration and optional calibration targets.
- Pick files for all 3 roles.
- Tap `Run Analysis`.
- Results are shown directly in the app and do not require internet.

## Notes

- ROI fields are active by default in both modes.
- Set ROI width/height to `0` to auto-expand to full remaining frame from `(x,y)`.
- If all ROI values are `0,0,0,0`, the role uses the full frame.
