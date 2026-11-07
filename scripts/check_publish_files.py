"""Check indexed Git files without printing detected credential values."""

import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def check():
    secrets = []
    for key, value in dotenv_values(ROOT / "apps/api/api.env").items():
        if (
            value
            and len(value) >= 16
            and any(label in key for label in ("KEY", "TOKEN", "PASSWORD", "DATABASE"))
        ):
            secrets.append(value.encode())
    login = ROOT / ".cache/access/login.txt"
    if login.exists() and len(login.read_text().strip()) >= 32:
        secrets.append(login.read_text().strip().encode())
    names = [name.decode() for name in git("ls-files", "-z").split(b"\0") if name]
    failures = []
    for name in names:
        path = Path(name)
        private_path = any(
            part in {".cache", ".venv", "node_modules", ".next", ".aws", ".secrets"}
            for part in path.parts
        )
        private_path |= path.name in {"api.env", "login.txt"} or (
            path.name.startswith(".env") and path.name != ".env.example"
        )
        if private_path:
            failures.append({"path": name, "reason": "private_path"})
            continue
        payload = git("show", ":" + name)
        if any(pattern.search(payload) for pattern in PATTERNS) or any(
            value in payload for value in secrets
        ):
            failures.append({"path": name, "reason": "credential_content"})
    return {"indexed_files_checked": len(names), "failures": failures}


if __name__ == "__main__":
    import json

    try:
        result = check()
        print(json.dumps(result, indent=2))
        raise SystemExit(1 if result["failures"] else 0)
    except Exception:
        print("publish_check_unavailable; sensitive details suppressed")
        raise SystemExit(1) from None
