#!/bin/bash
# SpecieScan - launcher for macOS.
# Double-click this file after 1-Install-SpecieScan.command has finished.

set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR" || exit 1

dialog() {
    osascript -e "display dialog \"$1\" buttons {\"OK\"} default button 1 with title \"SpecieScan\"" >/dev/null 2>&1
}

pause_close() {
    echo
    read -r -p "Press Return to close this window..." _
}

find_r() {
    local c
    for c in \
        "/Library/Frameworks/R.framework/Resources/bin/R" \
        "/usr/local/bin/R" \
        "/opt/homebrew/bin/R"; do
        if [ -x "$c" ]; then
            echo "$c"
            return 0
        fi
    done
    if command -v R >/dev/null 2>&1; then
        command -v R
        return 0
    fi
    return 1
}

if [ ! -x "$APP_DIR/.venv/bin/python" ] || [ ! -f "$APP_DIR/.setup_complete" ]; then
    dialog "SpecieScan is not installed yet. Please double-click 1-Install-SpecieScan.command first."
    echo "SpecieScan is not installed yet."
    echo "Please double-click 1-Install-SpecieScan.command first."
    pause_close
    exit 1
fi

R_BIN="$(find_r || true)"
if [ -z "$R_BIN" ]; then
    dialog "R could not be found. Please run 1-Install-SpecieScan.command again."
    echo "R could not be found. Please run 1-Install-SpecieScan.command again."
    pause_close
    exit 1
fi
export R_HOME="$("$R_BIN" RHOME)"
export PATH="$(dirname "$R_BIN"):$PATH"

# Use the same user R library that the installer populated.
R_LIBS_USER="$("$R_BIN" --slave -e 'cat(Sys.getenv("R_LIBS_USER"))')"
if [ -n "$R_LIBS_USER" ] && [ -d "$R_LIBS_USER" ]; then
    export R_LIBS_USER
fi

# Pick a free port, starting at 8080.
PORT="${PORT:-8080}"
TRIES=0
while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
    PORT=$((PORT + 1))
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 20 ]; then
        dialog "No free port was found. Please restart your Mac and try again."
        echo "No free port was found between 8080 and 8100."
        pause_close
        exit 1
    fi
done

export HOST="127.0.0.1"
export PORT
export OPEN_BROWSER="0"

echo "=============================================="
echo " SpecieScan is starting"
echo " Address: http://127.0.0.1:$PORT"
echo "=============================================="
echo "KEEP THIS WINDOW OPEN while you use SpecieScan."
echo "To stop the application: close this window or press Control+C."
echo

if [ "${NO_BROWSER:-0}" != "1" ]; then
    ( sleep 3; open "http://127.0.0.1:$PORT" ) &
fi

"$APP_DIR/.venv/bin/python" "$APP_DIR/app.py"
STATUS=$?

echo
if [ "$STATUS" -ne 0 ]; then
    dialog "SpecieScan stopped unexpectedly. Please read the message in the window, or run 1-Install-SpecieScan.command again."
    echo "SpecieScan stopped unexpectedly (exit code $STATUS)."
else
    echo "SpecieScan has stopped."
fi
pause_close
