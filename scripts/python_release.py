"""Seal pinned wheels and build separately verified, offline Python environments."""

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path
from uuid import uuid4

from scripts.local_release import RELEASES, ROOT, digest, verify_snapshot

WHEELS = RELEASES / "python-wheelhouse"
LOCK = ROOT / "apps/api/requirements-dev.lock.txt"


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_versions(payload):
    result = {}
    for line in payload.decode().splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line.strip())
        if not match or canonical(match[1]) in result:
            raise ValueError("requirements_must_be_unique_exact_pins")
        result[canonical(match[1])] = match[2]
    if not result:
        raise ValueError("requirements_empty")
    return result


def write_manifest(directory, kind, **metadata):
    files = {}
    for path in sorted(directory.rglob("*")):
        if path == directory / "manifest.json":
            continue
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("release_tree_link_rejected")
        if path.is_file():
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("release_tree_escape")
            files[path.relative_to(directory).as_posix()] = digest(path.read_bytes())
    manifest = {"format": 1, "kind": kind, **metadata, "files": files}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (directory / "manifest.json").write_bytes(encoded)
    return digest(encoded)


def seal_wheelhouse(directory=WHEELS, lock=LOCK):
    existing = directory / "manifest.json"
    if existing.exists():
        fingerprint = digest(existing.read_bytes())
        manifest = verify_snapshot(directory, fingerprint)
        if manifest["kind"] != "python-wheels" or manifest["requirements_sha256"] != digest(
            lock.read_bytes()
        ):
            raise ValueError("sealed_wheelhouse_lock_differs")
        return fingerprint
    pins = locked_versions(lock.read_bytes())
    found = {}
    for path in sorted(directory.glob("*.whl")):
        if path.is_symlink():
            raise ValueError("wheel_link_rejected")
        with zipfile.ZipFile(path) as archive:
            metadata = [i for i in archive.infolist() if i.filename.endswith(".dist-info/METADATA")]
            if len(metadata) != 1 or metadata[0].file_size > 1048576:
                raise ValueError("wheel_metadata_invalid")
            headers = Parser().parsestr(archive.read(metadata[0]).decode())
        name, version = canonical(headers["Name"]), headers["Version"]
        if pins.get(name) != version or name in found:
            raise ValueError("wheel_version_or_duplicate_rejected")
        found[name] = (version, digest(path.read_bytes()))
    if set(found) != set(pins):
        raise ValueError("wheelhouse_does_not_match_lock")
    hashed = "".join(
        f"{name}=={version} --hash=sha256:{fingerprint}\n"
        for name, (version, fingerprint) in sorted(found.items())
    )
    (directory / "requirements.hashes.txt").write_text(hashed, encoding="utf-8")
    fingerprint = write_manifest(
        directory, "python-wheels", packages=pins, requirements_sha256=digest(lock.read_bytes())
    )
    verify_snapshot(directory, fingerprint)
    return fingerprint


def minimal_environment():
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_CONFIG_FILE=os.devnull,
    )
    return env


def build_environment(wheel_hash, directory=WHEELS):
    wheels = verify_snapshot(directory, wheel_hash)
    root = RELEASES / "python" / str(uuid4())
    root.mkdir(parents=True)
    environment = root / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = minimal_environment()
    with (root / "build.log").open("w", encoding="utf-8") as output:
        for command in [
            [sys.executable, "-m", "venv", str(environment)],
            [
                str(python),
                "-B",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-cache-dir",
                "--no-compile",
                "--require-hashes",
                "--only-binary=:all:",
                "--find-links",
                str(directory),
                "-r",
                str(directory / "requirements.hashes.txt"),
            ],
            [str(python), "-B", "-m", "pip", "check"],
        ]:
            subprocess.run(command, env=env, stdout=output, stderr=output, check=True, timeout=300)
    probe = subprocess.run(
        [
            str(python),
            "-B",
            "-I",
            "-c",
            "import json,sys,importlib.metadata as m,fastapi,uvicorn,psycopg,zstandard,yaml; "
            "print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
            "'packages':{d.metadata['Name']:d.version for d in m.distributions()},"
            "'origins':[fastapi.__file__,uvicorn.__file__,psycopg.__file__]}))",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    result = json.loads(probe.stdout)
    actual = {canonical(name): version for name, version in result["packages"].items()}
    if {name: version for name, version in actual.items() if name != "pip"} != wheels["packages"]:
        raise ValueError("installed_packages_differ_from_lock")
    if Path(result["prefix"]).resolve() != environment.resolve():
        raise ValueError("python_environment_not_isolated")
    if any(
        not Path(path).resolve().is_relative_to(environment.resolve()) for path in result["origins"]
    ):
        raise ValueError("dependency_import_outside_environment")
    fingerprint = write_manifest(
        environment,
        "python-environment",
        packages=actual,
        wheelhouse_sha256=wheel_hash,
        host_python=sys.version.split()[0],
    )
    verify_snapshot(environment, fingerprint)
    return environment, python, fingerprint


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("seal", "build"))
    parser.add_argument("--wheelhouse-sha256")
    args = parser.parse_args()
    try:
        if args.operation == "seal":
            print(json.dumps({"wheelhouse_sha256": seal_wheelhouse()}))
        else:
            if not args.wheelhouse_sha256 or not re.fullmatch(
                "[a-f0-9]{64}", args.wheelhouse_sha256
            ):
                raise ValueError("trusted_wheelhouse_sha256_required")
            environment, python, fingerprint = build_environment(args.wheelhouse_sha256)
            print(
                json.dumps(
                    {
                        "environment": str(environment),
                        "python": str(python),
                        "manifest_sha256": fingerprint,
                        "wheelhouse_sha256": args.wheelhouse_sha256,
                    }
                )
            )
    except Exception as error:
        print(f"python_release_failed: {type(error).__name__}; details suppressed")
        raise SystemExit(1) from None
