"""Device-free managed-environment identity and locked dependency health checks."""

import importlib
import importlib.metadata
import json
import platform
import re
import sys
import sysconfig
from pathlib import Path

IMPORTS = {
    "appdirs": "appdirs",
    "certifi": "certifi",
    "charset-normalizer": "charset_normalizer",
    "defusedxml": "defusedxml.ElementTree",
    "idna": "idna",
    "ifaddr": "ifaddr",
    "lxml": "lxml.etree",
    "requests": "requests",
    "soco": "soco",
    "urllib3": "urllib3",
    "xmltodict": "xmltodict",
}


def interpreter_identity():
    return json.dumps(
        {
            "implementation": sys.implementation.name,
            "version": list(sys.version_info[:2]),
            "abi": sysconfig.get_config_var("SOABI"),
            "machine": platform.machine(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def check_environment(lock_path, expected_identity):
    if interpreter_identity() != expected_identity:
        raise ValueError("Interpreter identity differs")
    requirements = {}
    for line in Path(lock_path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "--hash=")):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?", line)
        if match is None:
            raise ValueError("Unsupported lock entry")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name not in IMPORTS or name in requirements:
            raise ValueError("Unreviewed or duplicate dependency")
        requirements[name] = match[2]
    if not requirements:
        raise ValueError("Empty dependency lock")
    for name, version in requirements.items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Installed dependency version differs")
        importlib.import_module(IMPORTS[name])


def main():
    try:
        if sys.argv[1:] == ["identity"]:
            print(interpreter_identity())
        elif len(sys.argv) == 4 and sys.argv[1] == "check":
            check_environment(sys.argv[2], sys.argv[3])
        else:
            raise ValueError("Invalid health check invocation")
    except Exception:  # noqa: BLE001 - imported dependency failures must produce bounded diagnostics
        print("Sonarchy environment health check failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
