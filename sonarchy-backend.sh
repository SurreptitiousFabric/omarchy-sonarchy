#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin"
export PATH

PLUGIN_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
DATA_DIR="${DATA_HOME}/sonarchy"
VENV_DIR="${DATA_DIR}/venv"
LOCK_FILE="${DATA_DIR}/setup.lock"
REQ_HASH_FILE="${VENV_DIR}/.requirements.sha256"
PYTHON_BIN="/usr/bin/python3"

setup_error() {
  printf 'SONOS_SETUP_ERROR: %s\n' "$*" >&2
  exit 1
}

umask 077

# The shell inherits the desktop session environment. Python startup hooks are
# not part of this plugin's trust boundary, so ignore them here. The pip step
# below receives a separate allowlisted environment.
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONINSPECT

command -v "$PYTHON_BIN" >/dev/null 2>&1 \
  || setup_error "Python 3.14 or newer is required."
"$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 14))' \
  || setup_error "Python 3.14 or newer is required."

if [[ -L "$PLUGIN_DIR" || -L "$PLUGIN_DIR/requirements.lock" ]]; then
  setup_error "Refusing to start from symbolic-link plugin files."
fi
if [[ ! -f "$PLUGIN_DIR/requirements.lock" ]]; then
  setup_error "The hash-locked dependency file is missing."
fi
if [[ -L "$DATA_DIR" || -L "$VENV_DIR" || -L "$LOCK_FILE" ]]; then
  setup_error "Refusing to use a symbolic link for the managed Sonarchy environment."
fi
install -d -m 700 "$DATA_DIR"
exec 9>"$LOCK_FILE"
flock 9

requirements_hash="$(sha256sum "$PLUGIN_DIR/requirements.lock" | awk '{print $1}')"
installed_hash=""
if [[ -f "$REQ_HASH_FILE" ]]; then
  installed_hash="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"
fi

if [[ ! -x "$VENV_DIR/bin/python" || "$installed_hash" != "$requirements_hash" ]]; then
  tmp_venv="${VENV_DIR}.tmp.$$"
  rm -rf "$tmp_venv"
  trap 'rm -rf "$tmp_venv"' EXIT
  if ! "$PYTHON_BIN" -m venv "$tmp_venv"; then
    setup_error "Could not create the Sonarchy Python environment."
  fi
  if ! env -i \
    HOME="$HOME" \
    PATH="/usr/bin:/bin" \
    LANG="${LANG:-C.UTF-8}" \
    PIP_CONFIG_FILE=/dev/null \
    "$tmp_venv/bin/python" -m pip install \
    --disable-pip-version-check \
    --no-input \
    --no-cache-dir \
    --no-deps \
    --only-binary=:all: \
    --require-hashes \
    --index-url https://pypi.org/simple \
    -r "$PLUGIN_DIR/requirements.lock" >&2; then
    setup_error "Could not install Sonarchy's hash-locked Python dependencies. Check the network connection and try again."
  fi
  printf '%s\n' "$requirements_hash" > "$tmp_venv/.requirements.sha256"
  rm -rf "$VENV_DIR"
  mv "$tmp_venv" "$VENV_DIR"
  trap - EXIT
fi

flock -u 9
exec "$VENV_DIR/bin/python" -B -u "$PLUGIN_DIR/sonarchy_service.py"
