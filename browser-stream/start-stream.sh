#!/usr/bin/env bash
set -e
export DISPLAY=:99
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
# A previous entrypoint can leave X11 children behind when the container is
# stopped abruptly. Remove those processes before starting a fresh display.
pkill -x Xvfb 2>/dev/null || true
pkill -x x11vnc 2>/dev/null || true
pkill -x fluxbox 2>/dev/null || true
pkill -x websockify 2>/dev/null || true
pkill -x chromium 2>/dev/null || true
pkill -x socat 2>/dev/null || true
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
mkdir -p /tmp/.X11-unix

cleanup() {
  pkill -x chromium 2>/dev/null || true
  pkill -x socat 2>/dev/null || true
  pkill -x websockify 2>/dev/null || true
  pkill -x x11vnc 2>/dev/null || true
  pkill -x fluxbox 2>/dev/null || true
  pkill -x Xvfb 2>/dev/null || true
  rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
}
trap cleanup EXIT INT TERM

Xvfb :99 -screen 0 1280x800x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
for i in $(seq 1 40); do
  if [ -S /tmp/.X11-unix/X99 ] && DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then break; fi
  sleep 0.25
done
if ! DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then
  echo "Xvfb failed to initialize display :99" >&2
  cat /tmp/xvfb.log >&2 || true
  exit 1
fi
fluxbox >/tmp/fluxbox.log 2>&1 &
DISPLAY=:99 x11vnc -display :99 -forever -shared -nopw -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
for i in $(seq 1 40); do
  (echo >/dev/tcp/127.0.0.1/5900) >/dev/null 2>&1 && break
  sleep 0.25
done
websockify --web=/usr/share/novnc 7900 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &
CHROMIUM_BIN=$(command -v chromium || command -v chromium-browser)
if [ -z "$CHROMIUM_BIN" ]; then
  echo 'Chromium executable was not found in the browser-stream image.' >&2
  exit 1
fi

# Keep the live preview clean and deterministic. A reused profile can trigger
# Chrome's "Restore pages" bubble, which hides agent clicks in the noVNC stream.
rm -rf /tmp/chrome-profile
mkdir -p /tmp/chrome-profile/Default
cat >/tmp/chrome-profile/Default/Preferences <<'EOF'
{
  "profile": {
    "exit_type": "Normal",
    "exited_cleanly": true
  },
  "session": {
    "restore_on_startup": 0
  }
}
EOF

"$CHROMIUM_BIN" \
  --no-sandbox \
  --disable-setuid-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --ozone-platform=x11 \
  --disable-features=UseOzonePlatform,Translate,OptimizationHints,MediaRouter,InterestFeedContentSuggestions,AutofillServerCommunication,ChromeWhatsNewUI,PrivacySandboxSettings4,SessionRestore \
  --no-first-run \
  --no-default-browser-check \
  --disable-default-apps \
  --disable-background-networking \
  --disable-component-update \
  --disable-session-crashed-bubble \
  --hide-crash-restore-bubble \
  --disable-infobars \
  --test-type \
  --password-store=basic \
  --use-mock-keychain \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port=9223 \
  --remote-allow-origins=* \
  --window-size=1280,800 \
  --user-data-dir=/tmp/chrome-profile \
  about:blank >/tmp/chromium.log 2>&1 &
for i in $(seq 1 40); do
  curl -fsS http://127.0.0.1:9223/json/version >/dev/null 2>&1 && break
  sleep 0.25
done
if ! curl -fsS http://127.0.0.1:9223/json/version >/dev/null 2>&1; then
  echo 'Chromium failed to expose CDP on internal port 9223.' >&2
  cat /tmp/chromium.log >&2 || true
  exit 1
fi
python3 /usr/local/bin/cdp-proxy.py 0.0.0.0 9222 127.0.0.1 9223 >/tmp/cdp-proxy.log 2>&1 &
for i in $(seq 1 40); do
  curl -fsS http://127.0.0.1:9222/json/version >/dev/null 2>&1 && break
  sleep 0.25
done
if ! curl -fsS http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo 'CDP proxy failed to expose port 9222.' >&2
  cat /tmp/cdp-proxy.log >&2 || true
  exit 1
fi
wait