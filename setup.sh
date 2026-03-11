#!/usr/bin/env bash
set -euo pipefail

# Accept all SDK licenses and install stable SDK tools before buildozer runs.
# This script is injected via volume mount and executed as the build entrypoint.

ANDROID_HOME="${HOME}/.buildozer/android/platform/android-sdk"
CMDLINE_TOOLS="${ANDROID_HOME}/cmdline-tools/latest/bin"

# Wait until cmdline-tools exist (buildozer creates them on first run).
# We pre-create the license directory so sdkmanager immediately accepts them.
mkdir -p "${ANDROID_HOME}/licenses"
echo "" > "${ANDROID_HOME}/licenses/android-sdk-license"
printf "\n24333f8a63b6825ea9c5514f83c2829b004d1fee" >> "${ANDROID_HOME}/licenses/android-sdk-license"
printf "\n8933bad161af4178b1185d1a37fbf41ea5269c55" >> "${ANDROID_HOME}/licenses/android-sdk-license"
printf "\nd56f5187479451eabf01fb78af6dfcb131a6481e" >> "${ANDROID_HOME}/licenses/android-sdk-license"
printf "\n84831b9409646a918e30573bab4c9c91346d8abd" >> "${ANDROID_HOME}/licenses/android-sdk-license"

echo "" > "${ANDROID_HOME}/licenses/android-sdk-preview-license"
printf "\n84831b9409646a918e30573bab4c9c91346d8abd" >> "${ANDROID_HOME}/licenses/android-sdk-preview-license"
printf "\n504667f4c0de7af1a06de9f4b1727b84351f2910" >> "${ANDROID_HOME}/licenses/android-sdk-preview-license"

echo "" > "${ANDROID_HOME}/licenses/android-sdk-arm-dbt-license"
printf "\n859f317696f67ef3d7f30a50a5560e7834b43903" >> "${ANDROID_HOME}/licenses/android-sdk-arm-dbt-license"

echo "" > "${ANDROID_HOME}/licenses/android-googletv-license"
printf "\n601085b94cd77f0b54ff86406957099ebe79c4d6" >> "${ANDROID_HOME}/licenses/android-googletv-license"

echo "" > "${ANDROID_HOME}/licenses/google-gdk-license"
printf "\n33b6a2b64607f11b759f320ef9dff4ae5c47d97a" >> "${ANDROID_HOME}/licenses/google-gdk-license"

echo "" > "${ANDROID_HOME}/licenses/mips-android-sysimage-license"
printf "\ne9acab5b5fbb560a72cfaecce8946896ff6aab9d" >> "${ANDROID_HOME}/licenses/mips-android-sysimage-license"

echo "[setup.sh] License files pre-populated."

# Run the actual buildozer build
exec buildozer "$@"
