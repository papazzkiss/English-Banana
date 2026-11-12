#!/usr/bin/env sh
# Build the Android debug APK: app URL -> Capacitor sync -> Gradle.
#   npm run android:build                                  (URL of the running tunnel)
#   BANANA_APP_URL=https://your.domain npm run android:build
# Needs JDK 21 (JAVA_HOME, or ~/.local/jdk-21*) and the Android SDK (ANDROID_HOME, or
# ~/Android/Sdk) with platform 36 and build-tools.
set -eu
cd "$(dirname "$0")/.."

if [ -z "${JAVA_HOME:-}" ]; then JAVA_HOME=$(ls -d "$HOME"/.local/jdk-21* 2>/dev/null | head -1); fi
: "${ANDROID_HOME:=$HOME/Android/Sdk}"
export JAVA_HOME ANDROID_HOME
[ -x "${JAVA_HOME}/bin/java" ] || { echo "JDK 21 not found: set JAVA_HOME" >&2; exit 1; }
[ -d "${ANDROID_HOME}/platforms" ] || { echo "Android SDK not found: set ANDROID_HOME" >&2; exit 1; }

node scripts/android-config.mjs
npx cap sync android
(cd android && ./gradlew assembleDebug)
echo "APK: $(pwd)/android/app/build/outputs/apk/debug/app-debug.apk"
