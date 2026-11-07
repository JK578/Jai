"""Package a relocatable Next standalone build; exclude environment files and caches."""

import json
from pathlib import Path
from uuid import uuid4

from scripts.local_release import RELEASES, ROOT, digest, verify_snapshot

FAULT = b"""// Deliberate candidate fault for the local rollback drill.
const faultHttp = require('node:http');
const originalEmit = faultHttp.Server.prototype.emit;
faultHttp.Server.prototype.emit = function(event, ...args) {
  if (event === 'request') {
    args[1].writeHead(503, {'Content-Type': 'text/plain', 'Cache-Control': 'no-store'});
    args[1].end('Candidate unavailable'); return true;
  }
  return originalEmit.call(this, event, ...args);
};
"""


def create_frontend_snapshot(web=ROOT / "apps/web", *, fault=False):
    standalone = web / ".next/standalone"
    entry = next(
        (p for p in [Path("server.js"), Path("apps/web/server.js")] if (standalone / p).is_file()),
        None,
    )
    if entry is None:
        raise ValueError("standalone_build_required")
    destination = RELEASES / "frontend" / str(uuid4())
    destination.mkdir(parents=True, exist_ok=False)
    files = {}

    def copy_tree(source, prefix):
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            parts = relative.parts
            next_cache = any(
                part == ".next" and parts[index + 1] in {"cache", "dev"}
                for index, part in enumerate(parts[:-1])
            )
            if next_cache or any(part.startswith(".env") or part == ".git" for part in parts):
                continue
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("standalone_link_not_relocatable")
            if not path.is_file():
                continue
            if not path.resolve().is_relative_to(source.resolve()):
                raise ValueError("standalone_path_outside_root")
            name = (prefix / relative).as_posix()
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = path.read_bytes()
            if fault and name == entry.as_posix():
                payload = FAULT + payload
            target.write_bytes(payload)
            files[name] = digest(payload)

    copy_tree(standalone, Path("."))
    copy_tree(web / ".next/static", entry.parent / ".next/static")
    if (web / "public").is_dir():
        copy_tree(web / "public", entry.parent / "public")
    manifest = {
        "format": 1,
        "kind": "frontend-standalone",
        "fault_injected": fault,
        "entrypoint": entry.as_posix(),
        "files": files,
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (destination / "manifest.json").write_bytes(encoded)
    fingerprint = digest(encoded)
    verify_snapshot(destination, fingerprint)
    return destination, fingerprint


if __name__ == "__main__":
    path, fingerprint = create_frontend_snapshot()
    print(json.dumps({"snapshot": str(path), "manifest_sha256": fingerprint}))
