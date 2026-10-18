"""Rolling release uploads are verified before the latest pointer can move."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/publish-latest-release.sh"
SHA = "a" * 40


def run_release(tmp_path, *, existing=False, upload_fail=False, sha=SHA, package=True):
    archive = tmp_path / "package.tar.gz"
    if package:
        archive.write_bytes(b"offline-package-test-content")
    calls = tmp_path / "calls.jsonl"
    gh = tmp_path / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        + """
import hashlib, json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args[:2] == ['release', 'view']:
    sys.exit(0 if os.environ['EXISTING'] == '1' else 1)
if args[:2] in (['release', 'upload'], ['release', 'create']):
    archive = pathlib.Path(args[3])
    checksum = pathlib.Path(args[4])
    digest, filename = checksum.read_text().split()
    assert filename == archive.name == 'ontofoundry-offline-latest.tar.gz'
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    if os.environ['UPLOAD_FAIL'] == '1':
        sys.exit(1)
"""
    )
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "GITHUB_REPOSITORY": "example/ontofoundry",
        "GITHUB_SHA": sha,
        "CALLS": str(calls),
        "EXISTING": str(int(existing)),
        "UPLOAD_FAIL": str(int(upload_fail)),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), str(archive)], env=env, capture_output=True, text=True
    )
    recorded = (
        [json.loads(line) for line in calls.read_text().splitlines()]
        if calls.exists()
        else []
    )
    return result, recorded


@pytest.mark.parametrize("existing", [False, True])
def test_latest_release_uploads_valid_checksum_and_only_updates_latest(tmp_path, existing):
    result, calls = run_release(tmp_path, existing=existing)
    assert result.returncode == 0, result.stderr
    assert not any("delete" in call for call in calls)
    if existing:
        assert [call[:2] for call in calls] == [
            ["release", "view"],
            ["release", "upload"],
            ["api", "--method"],
            ["release", "edit"],
        ]
        assert "repos/example/ontofoundry/git/refs/tags/latest" in calls[2]
        assert "sha=" + SHA in calls[2]
    else:
        assert calls[-1][:3] == ["release", "create", "latest"]
        assert calls[-1][calls[-1].index("--target") + 1] == SHA


def test_failed_upload_never_moves_tag_or_release_metadata(tmp_path):
    result, calls = run_release(tmp_path, existing=True, upload_fail=True)
    assert result.returncode != 0
    assert [call[:2] for call in calls] == [["release", "view"], ["release", "upload"]]


@pytest.mark.parametrize("kwargs", [{"package": False}, {"sha": "invalid"}])
def test_invalid_package_or_commit_never_touches_github(tmp_path, kwargs):
    result, calls = run_release(tmp_path, **kwargs)
    assert result.returncode != 0
    assert calls == []
