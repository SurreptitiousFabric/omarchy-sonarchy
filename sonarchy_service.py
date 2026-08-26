#!/usr/bin/env python3
from __future__ import annotations

import logging
import signal
import sys
from contextlib import suppress

from sonarchy_backend.controller import SonosController
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
    with suppress(KeyboardInterrupt):
        ProtocolServer(SonosController()).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
