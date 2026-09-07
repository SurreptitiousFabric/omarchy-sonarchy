#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$PLUGIN_DIR"
/usr/bin/python3 -I -S -B "$PLUGIN_DIR/sonarchy_runtime.py"
exec /usr/bin/python3 -B -u -m sonarchy_mcp.server
