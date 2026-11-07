import json

import pytest

from scripts import local_release


def fixture_source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    main = root / "apps/api/src/incidentiq/main.py"
    main.parent.mkdir(parents=True)
    main.write_text("available = app.state.started and config.ready\n")
    (root / "apps/api/api.env").write_text("PRIVATE_SECRET=must-not-package")
    private = root / ".cache/access"
    private.mkdir(parents=True)
    (private / "login.txt").write_text("must-not-package")
    monkeypatch.setattr(local_release, "RELEASES", tmp_path / "snapshots")
    return root


def test_snapshot_excludes_credentials_and_detects_tampering(tmp_path, monkeypatch):
    root = fixture_source(tmp_path, monkeypatch)
    snapshot, fingerprint = local_release.create_snapshot(root)
    manifest = local_release.verify_snapshot(snapshot, fingerprint)
    assert set(manifest["files"]) == {"apps/api/src/incidentiq/main.py"}
    source = snapshot / "apps/api/src/incidentiq/main.py"
    source.write_text("changed")
    with pytest.raises(ValueError, match="snapshot_file_changed"):
        local_release.verify_snapshot(snapshot, fingerprint)


def test_fault_candidate_differs_without_changing_baseline(tmp_path, monkeypatch):
    root = fixture_source(tmp_path, monkeypatch)
    first, original = local_release.create_snapshot(root)
    candidate, changed = local_release.create_snapshot(root, fault=True)
    assert original != changed
    assert local_release.verify_snapshot(first, original)["fault_injected"] is False
    assert local_release.verify_snapshot(candidate, changed)["fault_injected"] is True
    (candidate / "unexpected.txt").write_text("injected")
    with pytest.raises(ValueError, match="snapshot_unexpected_files"):
        local_release.verify_snapshot(candidate, changed)


def test_manifest_cannot_escape_snapshot_directory(tmp_path, monkeypatch):
    root = fixture_source(tmp_path, monkeypatch)
    snapshot, _ = local_release.create_snapshot(root)
    manifest = snapshot / "manifest.json"
    data = json.loads(manifest.read_text())
    data["files"]["../outside.txt"] = "0" * 64
    payload = json.dumps(data).encode()
    manifest.write_bytes(payload)
    with pytest.raises(ValueError, match="snapshot_path_invalid"):
        local_release.verify_snapshot(snapshot, local_release.digest(payload))
