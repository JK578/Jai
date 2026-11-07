import zipfile

import pytest

from scripts.local_release import verify_snapshot
from scripts.python_release import locked_versions, seal_wheelhouse, write_manifest


def fake_wheel(directory, name="sample_package", version="1.0"):
    path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{name}-{version}.dist-info/METADATA", f"Name: {name}\nVersion: {version}\n"
        )
    return path


def test_wheelhouse_requires_complete_pins_and_detects_changed_wheels(tmp_path):
    lock = tmp_path / "requirements.txt"
    lock.write_text("sample-package==1.0\n")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    with pytest.raises(ValueError, match="wheelhouse_does_not_match_lock"):
        seal_wheelhouse(wheels, lock)
    wheel = fake_wheel(wheels)
    fingerprint = seal_wheelhouse(wheels, lock)
    assert seal_wheelhouse(wheels, lock) == fingerprint
    assert "--hash=sha256:" in (wheels / "requirements.hashes.txt").read_text()
    verify_snapshot(wheels, fingerprint)
    wheel.write_bytes(wheel.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="snapshot_file_changed"):
        verify_snapshot(wheels, fingerprint)
    with pytest.raises(ValueError, match="snapshot_file_changed"):
        seal_wheelhouse(wheels, lock)


def test_unpinned_and_duplicate_requirements_fail_closed():
    for payload in (b"sample>=1", b"-r elsewhere", b"sample==1\nSample==1", b""):
        with pytest.raises(ValueError):
            locked_versions(payload)


def test_wrong_dependency_version_is_rejected(tmp_path):
    lock = tmp_path / "requirements.txt"
    lock.write_text("sample-package==1.0\n")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    fake_wheel(wheels, version="2.0")
    with pytest.raises(ValueError, match="wheel_version_or_duplicate_rejected"):
        seal_wheelhouse(wheels, lock)


def test_environment_manifest_rejects_extra_or_changed_dependency(tmp_path):
    (tmp_path / "dependency.py").write_text("approved")
    fingerprint = write_manifest(tmp_path, "python-environment")
    verify_snapshot(tmp_path, fingerprint)
    (tmp_path / "injected.py").write_text("unexpected")
    with pytest.raises(ValueError, match="snapshot_unexpected_files"):
        verify_snapshot(tmp_path, fingerprint)
