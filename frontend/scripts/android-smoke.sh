#!/usr/bin/env bash
set -euo pipefail

APK="${APK_PATH:-ATLAS-AI-android.apk}"
PACKAGE="com.atlasai.family"
ACTIVITY="$PACKAGE/.MainActivity"

echo "APK: $(ls -lh "$APK")"
adb start-server
adb devices
adb wait-for-device

BOOTED=""
for _ in $(seq 1 90); do
  BOOTED="$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)"
  if [ "$BOOTED" = "1" ]; then
    break
  fi
  sleep 2
done
if [ "$BOOTED" != "1" ]; then
  echo "::error::L'emulatore non ha completato il boot"
  adb devices || true
  exit 1
fi

adb logcat -c || true
adb shell input keyevent 82 || true
adb shell getprop ro.product.cpu.abi || true
adb shell getprop ro.build.version.sdk || true
adb shell df -h /data || true

INSTALL_STATUS=0
for attempt in 1 2 3; do
  if adb install -r "$APK" > /tmp/atlas-install.log 2>&1; then
    INSTALL_STATUS=0
    break
  fi
  INSTALL_STATUS=$?
  echo "Tentativo installazione $attempt fallito (exit $INSTALL_STATUS)"
  cat /tmp/atlas-install.log || true
  sleep 5
done
cat /tmp/atlas-install.log || true

if [ "$INSTALL_STATUS" -ne 0 ]; then
  echo "::error::adb install fallito (exit $INSTALL_STATUS): $(tail -c 1200 /tmp/atlas-install.log | tr '\n' ' ')"
  adb logcat -d -v brief > android-logcat.txt || true
  adb shell dumpsys package "$PACKAGE" > android-package.txt 2>&1 || true
  adb exec-out screencap -p > atlas-install.png || true
  exit 1
fi

adb shell am force-stop "$PACKAGE" || true
adb shell am start -W -n "$ACTIVITY" || true
sleep 15

dump_ui() {
  adb shell uiautomator dump /sdcard/atlas-window.xml >/dev/null 2>&1 || true
  adb pull /sdcard/atlas-window.xml atlas-window.xml >/dev/null 2>&1 || true
}

dump_ui
if grep -q "isn't responding" atlas-window.xml 2>/dev/null; then
  echo "Dialogo ANR di sistema rilevato; lo chiudo"
  adb shell input keyevent 4 || true
  sleep 2
  dump_ui
fi

PID="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
echo "Processo ATLAS: '$PID'"
adb logcat -d -v brief > android-logcat.txt || true

if [ -z "$PID" ]; then
  tail -120 android-logcat.txt || true
  echo "::error::Il processo ATLAS non è attivo dopo il lancio"
  adb shell dumpsys package "$PACKAGE" > android-package.txt 2>&1 || true
  adb exec-out screencap -p > atlas-install.png || true
  exit 1
fi

for _ in 1 2 3; do
  if grep -Eq 'ATLAS AI|Chi sei|Inserisci PIN|PIN' atlas-window.xml 2>/dev/null; then
    break
  fi
  sleep 3
  dump_ui
done
if ! grep -Eq 'ATLAS AI|Chi sei|Inserisci PIN|PIN' atlas-window.xml 2>/dev/null; then
  tail -120 android-logcat.txt || true
  echo "::error::La UI ATLAS non è comparsa dopo il lancio"
  adb exec-out screencap -p > atlas-install.png || true
  exit 1
fi

if grep -q 'FATAL EXCEPTION' android-logcat.txt; then
  echo "::error::Crash Android rilevato nel logcat"
  grep -A 20 'FATAL EXCEPTION' android-logcat.txt || true
  adb exec-out screencap -p > atlas-install.png || true
  exit 1
fi

adb exec-out screencap -p > atlas-install.png || true
echo "::notice::APK installato e avviato, processo $PID"
