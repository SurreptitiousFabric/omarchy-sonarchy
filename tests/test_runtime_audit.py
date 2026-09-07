from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_runtime as audit

CANDIDATE = "a" * 40


def test_ci_requires_runtime_audit():
    workflow = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()
    assert '-m scripts.audit_runtime "$GITHUB_SHA"' in workflow
    assert "continue-on-error" not in workflow


def test_complete_audit_records_exact_lock_versions_and_candidate(monkeypatch):
    calls = []
    monkeypatch.setattr(audit, "query", lambda name, version: calls.append((name, version)) or {})
    result = audit.audit(CANDIDATE)
    assert result["status"] == "clean"
    assert result["candidate"] == CANDIDATE
    assert len(result["lockSha256"]) == 64
    assert len(calls) == 11
    assert ("soco", "0.31.2") in calls
    assert calls == [(item["name"], item["version"]) for item in result["packages"]]


def test_known_advisory_fixture_fails_cli(monkeypatch, capsys):
    monkeypatch.setattr(audit.sys, "argv", ["audit", CANDIDATE])

    # Recorded advisory ID: https://osv.dev/vulnerability/PYSEC-2018-28.
    # Injected HTTP response, NOT a claim that our current requests pin is affected.
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, limit):
            assert limit == audit.MAX_RESPONSE + 1
            return b'{"vulns":[{"id":"PYSEC-2018-28","details":"private-marker"}]}'

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == audit.ENDPOINT
            assert timeout == 15
            return Response()

    monkeypatch.setattr(audit, "build_opener", lambda *_: Opener())
    assert audit.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "advisories"
    assert "PYSEC-2018-28" in output
    assert "private-marker" not in output


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"error": "private-marker"},
        {"vulns": None},
        {"vulns": {}},
        {"vulns": [None]},
        {"vulns": [{}]},
        {"vulns": [{"id": "bad\nidentifier"}]},
        {"next_page_token": "more"},
        {"next_page_token": None},
    ],
)
def test_incomplete_response_never_reports_clean(monkeypatch, capsys, payload):
    monkeypatch.setattr(audit.sys, "argv", ["audit", CANDIDATE])
    monkeypatch.setattr(audit, "query", lambda *_: payload)
    assert audit.main() == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "incomplete"
    assert "private-marker" not in output


def test_network_failure_after_partial_success_is_not_clean(monkeypatch, capsys):
    count = 0

    def query(*_):
        nonlocal count
        count += 1
        if count == 2:
            raise TimeoutError("private-marker")
        return {}

    monkeypatch.setattr(audit, "query", query)
    monkeypatch.setattr(audit.sys, "argv", ["audit", CANDIDATE])
    assert audit.main() == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "incomplete"
    assert "private-marker" not in output
    assert count == 2


def test_environment_mismatch_fails_before_network(tmp_path, monkeypatch):
    lock = tmp_path / "requirements.lock"
    lock.write_text("soco==0.0.0\n")
    monkeypatch.setattr(audit, "query", lambda *_: pytest.fail("must not query"))
    with pytest.raises(ValueError, match="version differs"):
        audit.audit(CANDIDATE, lock)


@pytest.mark.parametrize("candidate", ["main", "", "abc", "x" * 40])
def test_exact_candidate_required(candidate):
    with pytest.raises(ValueError):
        audit.audit(candidate)


@pytest.mark.parametrize(
    "status,raw",
    [(503, b"private-marker"), (200, b"x" * (audit.MAX_RESPONSE + 1)), (200, b"not json")],
)
def test_http_failures_are_rejected(monkeypatch, status, raw):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, limit):
            assert limit == audit.MAX_RESPONSE + 1
            return raw

    response = Response()
    response.status = status

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == audit.ENDPOINT
            assert timeout == 15
            assert json.loads(request.data) == {
                "package": {"name": "soco", "ecosystem": "PyPI"},
                "version": "0.31.2",
            }
            return response

    monkeypatch.setattr(audit, "build_opener", lambda *_: Opener())
    with pytest.raises(ValueError):
        audit.query("soco", "0.31.2")


def test_redirect_is_refused():
    with pytest.raises(ValueError, match="redirect"):
        audit.NoRedirect().redirect_request(None, None, 302, None, None, "https://example.com")
