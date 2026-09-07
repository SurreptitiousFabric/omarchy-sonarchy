"""Fail-closed OSV audit of the exact public runtime lock and installed versions."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from sonarchy_environment import IMPORTS, check_environment, interpreter_identity

ENDPOINT = "https://api.osv.dev/v1/query"
MAX_RESPONSE = 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Audit redirect refused")


def query(package, version):
    request = Request(
        ENDPOINT,
        data=json.dumps(
            {"package": {"name": package, "ecosystem": "PyPI"}, "version": version}
        ).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    # Do not inherit credential-bearing proxy settings or follow redirects.
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError("Audit HTTP failure")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("Audit response too large")
        return json.loads(raw)


def advisory_ids(payload):
    if not isinstance(payload, dict) or set(payload) - {"vulns", "next_page_token"}:
        raise ValueError("Invalid audit response")
    # Pagination is never silently truncated: require a later complete rerun.
    if payload.get("next_page_token") or (
        "next_page_token" in payload and not isinstance(payload["next_page_token"], str)
    ):
        raise ValueError("Incomplete audit response")
    vulns = payload.get("vulns", [])
    if not isinstance(vulns, list) or len(vulns) > 1000:
        raise ValueError("Invalid advisory list")
    ids = set()
    for vuln in vulns:
        if not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str):
            raise ValueError("Invalid advisory")
        identifier = vuln["id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", identifier):
            raise ValueError("Invalid advisory identifier")
        ids.add(identifier)
    return sorted(ids)


def audit(candidate, lock_path=ROOT / "requirements.lock"):
    if not re.fullmatch(r"[a-f0-9]{40}", candidate):
        raise ValueError("Exact candidate commit required")
    raw = lock_path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("Lock too large")
    check_environment(lock_path, interpreter_identity())
    versions = {}
    for line in raw.decode().splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "--hash=")):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9.!+_-]{1,128})\s*\\?", line)
        if match is None:
            raise ValueError("Unsupported lock entry")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name not in IMPORTS or name in versions:
            raise ValueError("Unreviewed dependency")
        versions[name] = match[2]
    if not versions or len(versions) > 32:
        raise ValueError("Invalid dependency count")
    packages = [
        {"name": name, "version": version, "advisories": advisory_ids(query(name, version))}
        for name, version in sorted(versions.items())
    ]
    return {
        "status": "advisories" if any(item["advisories"] for item in packages) else "clean",
        "source": ENDPOINT,
        "candidate": candidate,
        "lockSha256": hashlib.sha256(raw).hexdigest(),
        "queriedAt": datetime.now(UTC).isoformat(),
        "packages": packages,
    }


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError("Exact candidate commit required")
        result = audit(sys.argv[1])
    except Exception:  # noqa: BLE001 - never echo remote bodies, paths or environment metadata
        print(
            json.dumps(
                {"status": "incomplete", "message": "Runtime advisory audit failed; not clean."}
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "clean" else 1


if __name__ == "__main__":
    sys.exit(main())
