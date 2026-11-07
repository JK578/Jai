import pytest

from scripts import frontend_release
from scripts.local_release import verify_snapshot


def build_fixture(tmp_path, monkeypatch):
    web = tmp_path / "web"
    standalone = web / ".next/standalone"
    standalone.mkdir(parents=True)
    (standalone / "server.js").write_text("console.log('standalone');")
    (standalone / ".env.local").write_text("PRIVATE_TOKEN=must-not-package")
    dependency = standalone / "node_modules/next/dist/server/dev"
    dependency.mkdir(parents=True)
    (dependency / "required-in-production.js").write_text("module.exports = {};")
    cache = standalone / ".next/cache"
    cache.mkdir(parents=True)
    (cache / "private-cache.txt").write_text("must-not-package")
    static = web / ".next/static"
    static.mkdir()
    (static / "app.css").write_text("body { color: teal; }")
    monkeypatch.setattr(frontend_release, "RELEASES", tmp_path / "releases")
    return web


def test_frontend_snapshot_copies_assets_without_environment_files(tmp_path, monkeypatch):
    web = build_fixture(tmp_path, monkeypatch)
    artifact, fingerprint = frontend_release.create_frontend_snapshot(web)
    manifest = verify_snapshot(artifact, fingerprint)
    assert manifest["kind"] == "frontend-standalone"
    assert set(manifest["files"]) == {
        "server.js",
        ".next/static/app.css",
        "node_modules/next/dist/server/dev/required-in-production.js",
    }
    assert not (artifact / ".env.local").exists()
    (artifact / ".next/static/app.css").write_text("tampered")
    with pytest.raises(ValueError, match="snapshot_file_changed"):
        verify_snapshot(artifact, fingerprint)


def test_fault_injection_is_separate_from_baseline(tmp_path, monkeypatch):
    web = build_fixture(tmp_path, monkeypatch)
    baseline, baseline_hash = frontend_release.create_frontend_snapshot(web)
    candidate, candidate_hash = frontend_release.create_frontend_snapshot(web, fault=True)
    assert baseline_hash != candidate_hash
    assert (candidate / "server.js").read_bytes().startswith(frontend_release.FAULT)
    assert not (baseline / "server.js").read_bytes().startswith(frontend_release.FAULT)
    assert (web / ".next/standalone/server.js").read_text() == "console.log('standalone');"


def test_frontend_snapshot_requires_a_build(tmp_path, monkeypatch):
    monkeypatch.setattr(frontend_release, "RELEASES", tmp_path / "releases")
    with pytest.raises(ValueError, match="standalone_build_required"):
        frontend_release.create_frontend_snapshot(tmp_path / "unbuilt")
