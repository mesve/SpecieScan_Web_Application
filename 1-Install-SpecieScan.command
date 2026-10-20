#!/bin/bash
# SpecieScan - one-time installer for macOS.
# Double-click this file. Everything is installed into this folder.

set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR" || exit 1
LOG="$APP_DIR/setup_log.txt"
exec > >(tee -a "$LOG") 2>&1

DIALOG_TITLE="SpecieScan setup"

dialog() {
    osascript -e "display dialog \"$1\" buttons {\"OK\"} default button 1 with title \"$DIALOG_TITLE\"" >/dev/null 2>&1
}

pause_close() {
    echo
    read -r -p "Press Return to close this window..." _
}

fail() {
    echo
    echo "ERROR: $1"
    echo "Details were saved to: $LOG"
    dialog "Setup could not finish. $1 The file setup_log.txt contains the details."
    pause_close
    exit 1
}

find_python() {
    local c
    for c in \
        "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10" \
        "/usr/local/bin/python3.10" \
        "/opt/homebrew/bin/python3.10" \
        "$HOME/anaconda3/bin/python3.10" \
        "$HOME/anaconda3/bin/python3" \
        "$HOME/miniconda3/bin/python3"; do
        if [ -x "$c" ] && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)' >/dev/null 2>&1; then
            echo "$c"
            return 0
        fi
    done
    if command -v python3.10 >/dev/null 2>&1; then
        command -v python3.10
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        c="$(command -v python3)"
        if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)' >/dev/null 2>&1; then
            echo "$c"
            return 0
        fi
    fi
    return 1
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

echo "=============================================="
echo " SpecieScan - one-time installation (macOS)"
echo "=============================================="
echo "Log file: $LOG"
echo

if [ "$(uname -s)" != "Darwin" ]; then
    fail "This installer is for macOS only."
fi

# ---------------------------------------------------------------- Python 3.10
PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
    echo "Python 3.10 was not found."
    open "https://www.python.org/downloads/release/python-31011/"
    fail "Python 3.10 is required. The download page has been opened. Install Python 3.10.11, then double-click this file again."
fi
echo "Using Python: $PYTHON ($("$PYTHON" --version 2>&1))"

# ------------------------------------------------------------------------ R
R_BIN="$(find_r || true)"
if [ -z "$R_BIN" ]; then
    echo "R was not found."
    open "https://cran.r-project.org/bin/macosx/"
    fail "R is required. The download page has been opened. Install R 4.2.3, then double-click this file again."
fi
export R_HOME="$("$R_BIN" RHOME)"
export PATH="$(dirname "$R_BIN"):$PATH"
R_VERSION="$("$R_BIN" --version 2>/dev/null | head -n 1)"
echo "Using R: $R_BIN"
echo "R home: $R_HOME"
echo "R version: $R_VERSION"

# ------------------------------------------------------------ Python packages
VENV="$APP_DIR/.venv"
if [ -x "$VENV/bin/python" ]; then
    echo "Using the existing private Python environment."
else
    echo "Creating a private Python environment (this may take a minute)..."
    "$PYTHON" -m venv "$VENV" || fail "Could not create the Python environment."
fi

echo "Installing Python packages..."
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel || fail "Could not update pip. Check your internet connection."

# Apple Silicon + Python 3.10 has no prebuilt rpy2 wheel on PyPI, so pip would
# compile it (requiring Xcode Command Line Tools). Use the wheel shipped here.
if [ "$(uname -m)" = "arm64" ] && [ -f "$APP_DIR/vendor/rpy2-3.5.15-cp310-cp310-macosx_11_0_arm64.whl" ]; then
    echo "Using the included Apple Silicon rpy2 package (no compiler needed)."
    "$VENV/bin/python" -m pip install "$APP_DIR/vendor/rpy2-3.5.15-cp310-cp310-macosx_11_0_arm64.whl" || fail "Could not install the included rpy2 package."
fi

"$VENV/bin/python" -m pip install -r "$APP_DIR/requirements.txt" || fail "Could not install the Python packages. Check your internet connection."

# --------------------------------------------------------------- R packages
# Install into the user's own R library so no administrator password is needed.
R_LIBS_USER="$("$R_BIN" --slave -e 'cat(Sys.getenv("R_LIBS_USER"))')"
if [ -n "$R_LIBS_USER" ]; then
    mkdir -p "$R_LIBS_USER"
    export R_LIBS_USER
    echo "R package library: $R_LIBS_USER"
fi

echo "Installing R packages (this can take several minutes)..."
R_SCRIPT="$(mktemp /tmp/specie_scan_r.XXXXXX.R)"
trap 'rm -f "$R_SCRIPT"' EXIT
cat > "$R_SCRIPT" <<'RS'
options(repos = c(CRAN = "https://cloud.r-project.org"))
need <- function(p) !requireNamespace(p, quietly = TRUE)
if (need("BiocManager")) install.packages("BiocManager")
if (need("mzR")) BiocManager::install("mzR", ask = FALSE, update = FALSE)
if (need("MALDIquant")) install.packages("MALDIquant")
if (need("MALDIquantForeign")) install.packages("MALDIquantForeign")
ok <- all(vapply(c("MALDIquant", "MALDIquantForeign", "mzR"),
                 requireNamespace, logical(1), quietly = TRUE))
if (!ok) quit(status = 1)
cat("R packages OK\n")
RS
"$R_BIN" --slave --no-save -f "$R_SCRIPT" || fail "Could not install the R packages. Check your internet connection."
rm -f "$R_SCRIPT"

# --------------------------------------------------------------- final check
echo "Checking that Python can use R..."
"$VENV/bin/python" - <<'PY' || fail "R is installed, but Python could not load it. Please send the setup_log.txt file to the developer."
import rpy2.robjects as ro
ro.r('library(MALDIquant); library(MALDIquantForeign); library(mzR)')
print('R integration OK')
PY

{
    echo "Installed on $(date)"
    echo "Python: $("$VENV/bin/python" --version 2>&1)"
    echo "R: $R_VERSION"
    echo "R_HOME: $R_HOME"
} > "$APP_DIR/.setup_complete"

echo
echo "=============================================="
echo " Installation complete."
echo " Double-click 2-Start-SpecieScan.command next."
echo "=============================================="
dialog "Installation complete. Double-click 2-Start-SpecieScan.command to open SpecieScan."
exit 0
