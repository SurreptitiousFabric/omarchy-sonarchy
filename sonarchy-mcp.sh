#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$PLUGIN_DIR"
exec /usr/bin/python3 -B -u -m sonarchy_mcp.server
