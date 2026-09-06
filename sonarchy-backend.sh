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
IDENTITY_FILE="${VENV_DIR}/.python-identity"
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

# Reject unsafe plugin paths before executing repository-owned Python.
if [[ -L "$PLUGIN_DIR" || -L "$PLUGIN_DIR/requirements.lock" ]]; then
  setup_error "Refusing to start from symbolic-link plugin files."
fi

command -v "$PYTHON_BIN" >/dev/null 2>&1 \
  || setup_error "Stable CPython 3.14.x is required."
"$PYTHON_BIN" -I -S -B "$PLUGIN_DIR/sonarchy_runtime.py" \
  || setup_error "Stable CPython 3.14.x is required; other versions are unvalidated."

if [[ ! -f "$PLUGIN_DIR/requirements.lock" ]]; then
  setup_error "The hash-locked dependency file is missing."
fi
if [[ -L "$DATA_DIR" || -L "$VENV_DIR" || -L "$LOCK_FILE" ]]; then
  setup_error "Refusing to use a symbolic link for the managed Sonarchy environment."
fi
install -d -m 700 "$DATA_DIR"
exec 9>"$LOCK_FILE"
flock 9

if [[ -L "$REQ_HASH_FILE" || -L "$IDENTITY_FILE" ]]; then
  setup_error "Refusing symbolic-link environment metadata."
fi
python_identity="$(timeout --kill-after=1 10 "$PYTHON_BIN" -I -S -B "$PLUGIN_DIR/sonarchy_environment.py" identity)" \
  || setup_error "Could not identify the supported Python interpreter."

environment_healthy() {
  timeout --kill-after=1 10 "$1/bin/python" -I -B "$PLUGIN_DIR/sonarchy_environment.py" \
    check "$PLUGIN_DIR/requirements.lock" "$python_identity" >/dev/null 2>&1
}

requirements_hash="$(sha256sum "$PLUGIN_DIR/requirements.lock" | awk '{print $1}')"
installed_hash=""
if [[ -f "$REQ_HASH_FILE" ]]; then
  installed_hash="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"
fi

installed_identity=""
if [[ -f "$IDENTITY_FILE" ]]; then
  installed_identity="$(cat "$IDENTITY_FILE")"
fi
if [[ ! -x "$VENV_DIR/bin/python" || "$installed_hash" != "$requirements_hash" \
  || "$installed_identity" != "$python_identity" ]] || ! environment_healthy "$VENV_DIR"; then
  tmp_venv="$(mktemp -d "$DATA_DIR/venv.build.XXXXXX")"
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
  if ! environment_healthy "$tmp_venv"; then
    setup_error "Replacement Python environment failed validation; the previous environment was preserved."
  fi
  printf '%s\n' "$requirements_hash" > "$tmp_venv/.requirements.sha256"
  printf '%s\n' "$python_identity" > "$tmp_venv/.python-identity"
  previous_venv=""
  if [[ -e "$VENV_DIR" ]]; then
    previous_venv="$(mktemp -d "$DATA_DIR/venv.previous.XXXXXX")"
    rmdir "$previous_venv"
    mv -T "$VENV_DIR" "$previous_venv"
  fi
  if ! mv -T "$tmp_venv" "$VENV_DIR"; then
    if [[ -n "$previous_venv" ]]; then
      mv -T "$previous_venv" "$VENV_DIR" \
        || setup_error "Promotion failed; the previous environment remains in the private data directory."
    fi
    setup_error "Could not promote the replacement environment; the previous environment was preserved."
  fi
  trap - EXIT
  if [[ -n "$previous_venv" ]]; then
    rm -rf "$previous_venv"
  fi
fi

flock -u 9
exec "$VENV_DIR/bin/python" -B -u "$PLUGIN_DIR/sonarchy_service.py"
