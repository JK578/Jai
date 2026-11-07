"""Credential-free, manifest-verified backend source snapshots for local rollback."""

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / ".cache/releases"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def source_paths(root):
    for directory in ("apps/api/src", "apps/api/migrations", "scripts"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json", ".txt"}:
                if "__pycache__" not in path.parts:
                    yield path
    for name in ("pyproject.toml", "requirements-dev.lock.txt", "alembic.ini"):
        path = root / "apps/api" / name
        if path.is_file():
            yield path


def create_snapshot(root=ROOT, *, fault=False):
    destination = RELEASES / str(uuid4())
    destination.mkdir(parents=True, exist_ok=False)
    files = {}
    for source in source_paths(root):
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError("snapshot_source_outside_root")
        name = source.relative_to(root).as_posix()
        payload = source.read_bytes()
        if fault and name == "apps/api/src/incidentiq/main.py":
            original = b"available = app.state.started and config.ready"
            if payload.count(original) != 1:
                raise ValueError("fault_fixture_target_changed")
            payload = payload.replace(original, b"available = False  # rollback drill fault")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        files[name] = digest(payload)
    if "apps/api/src/incidentiq/main.py" not in files:
        raise ValueError("snapshot_api_missing")
    manifest = {
        "format": 1,
        "kind": "backend-source",
        "fault_injected": fault,
        "python": sys.version.split()[0],
        "files": files,
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (destination / "manifest.json").write_bytes(encoded)
    return destination, digest(encoded)


def verify_snapshot(directory, expected):
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("snapshot_manifest_symlink")
    encoded = manifest_path.read_bytes()
    if digest(encoded) != expected:
        raise ValueError("snapshot_manifest_changed")
    manifest = json.loads(encoded)
    if manifest["format"] != 1 or manifest["kind"] not in {
        "backend-source",
        "frontend-standalone",
        "python-wheels",
        "python-environment",
    }:
        raise ValueError("snapshot_format_invalid")
    for name, fingerprint in manifest["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("snapshot_path_invalid")
        target = directory / name
        if target.is_symlink() or not target.resolve().is_relative_to(directory.resolve()):
            raise ValueError("snapshot_path_outside_root")
        if digest(target.read_bytes()) != fingerprint:
            raise ValueError("snapshot_file_changed")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("snapshot_unexpected_files")
    return manifest


if __name__ == "__main__":
    path, fingerprint = create_snapshot()
    verify_snapshot(path, fingerprint)
    print(json.dumps({"snapshot": str(path), "manifest_sha256": fingerprint}))
