#!/usr/bin/env python3
from __future__ import annotations

import logging
import signal
import sys
from contextlib import suppress

from sonarchy_backend.controller import SonosController
from sonarchy_backend.local_mcp import BackendOwnership, MultiClientRuntime, load_mcp_permissions
from sonarchy_backend.protocol import ProtocolServer


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def stop_service(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    try:
        ownership = BackendOwnership.acquire()
    except RuntimeError as exc:
        logging.error("Sonarchy backend ownership unavailable: %s", exc)
        return 1
    with ownership, suppress(KeyboardInterrupt):
        listener = ownership.open_listener()
        # Ownership is acquired before controller construction or discovery.
        protocol = ProtocolServer(SonosController())
        MultiClientRuntime(protocol, listener, load_mcp_permissions()).serve(
            sys.stdin.buffer, sys.stdout.buffer
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
