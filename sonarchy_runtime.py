"""Dependency-free startup guard; keep syntax readable by older interpreters."""

import sys

RUNTIME_REQUIREMENT = "Sonarchy requires stable CPython 3.14.x; other versions are unvalidated."


def supported_runtime(version, implementation):
    return implementation == "cpython" and version[:2] == (3, 14) and version[3] == "final"


def main():
    if supported_runtime(sys.version_info, sys.implementation.name):
        return 0
    print(RUNTIME_REQUIREMENT, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
