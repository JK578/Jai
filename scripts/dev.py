"""Install once, then run both local services. Uses only the Python standard library."""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LOGS = ROOT / ".cache/dev"


def tools():
    node, npm = shutil.which("node"), shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise ValueError("Install Node 24 and npm 11, then open a new terminal.")
    if (
        json.loads(
            subprocess.check_output(
                [node, "-p", "JSON.stringify(process.versions.node)"], text=True
            )
        ).split(".")[0]
        != "24"
    ):
        raise ValueError("This project requires Node 24.")
    npm_cli = Path(npm).parent / "node_modules/npm/bin/npm-cli.js"
    npm_command = [node, str(npm_cli)] if npm_cli.is_file() else [npm]
    if (
        subprocess.check_output([*npm_command, "--version"], text=True).strip().split(".")[0]
        != "11"
    ):
        raise ValueError("This project requires npm 11.")
    return node, npm_command


def copy_defaults():
    for source, target in [
        ("apps/api/.env.example", "apps/api/api.env"),
        ("apps/web/.env.example", "apps/web/.env.local"),
    ]:
        try:
            with (ROOT / target).open("xb") as output:
                output.write((ROOT / source).read_bytes())
        except FileExistsError:
            pass


def setup():
    if sys.version_info[:2] != (3, 15):
        raise ValueError("Run setup with Python 3.15: py -3.15 scripts/dev.py setup")
    node, npm = tools()
    if not PYTHON.exists():
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    version = subprocess.check_output(
        [str(PYTHON), "-c", "import sys;print(sys.version_info[:2])"], text=True
    ).strip()
    if version != "(3, 15)":
        raise ValueError("Recreate .venv with Python 3.15; do not copy it between machines.")
    for args in [
        [str(PYTHON), "scripts/build_phase5_wheels.py"],
        [
            str(PYTHON),
            "-m",
            "pip",
            "install",
            "--only-binary=:all:",
            "--find-links",
            ".cache/phase5-wheels",
            "-r",
            "apps/api/requirements-dev.lock.txt",
        ],
        [str(PYTHON), "-m", "pip", "install", "--no-deps", "-e", "apps/api"],
    ]:
        subprocess.run(args, cwd=ROOT, check=True)
    subprocess.run([*npm, "ci", "--no-fund", "--no-audit"], cwd=ROOT / "apps/web", check=True)
    copy_defaults()
    subprocess.run(
        [node, "node_modules/next/dist/bin/next", "build", "--webpack"],
        cwd=ROOT / "apps/web",
        check=True,
    )
    frontend_entry()
    print("Setup complete. Basic demo: py -3.15 scripts/dev.py run --basic")
    print("Full flow: configure private database access, then py -3.15 scripts/dev.py run")


def frontend_entry():
    web = ROOT / "apps/web"
    standalone = web / ".next/standalone"
    for relative in (Path("server.js"), Path("apps/web/server.js")):
        entry = standalone / relative
        if entry.is_file():
            shutil.copytree(web / ".next/static", entry.parent / ".next/static", dirs_exist_ok=True)
            if (web / "public").is_dir():
                shutil.copytree(web / "public", entry.parent / "public", dirs_exist_ok=True)
            return entry
    raise ValueError("Frontend build missing. Run py -3.15 scripts/dev.py setup.")


def available(port):
    if not 1024 <= port <= 65535:
        raise ValueError("Use a port between 1024 and 65535.")
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            raise ValueError(
                f"Port {port} is busy. Choose another port; existing processes are left running."
            ) from None


def stop(child):
    if child.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(child.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(child.pid, signal.SIGKILL)
        else:
            child.kill()
        child.wait(timeout=5)


def wait_ready(url, children, timeout=120):
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(child.poll() is not None for child in children):
            raise ValueError("A service exited. Check the private logs in .cache/dev/.")
        try:
            with opener.open(url, timeout=3) as response:
                if response.status == 200:
                    return
        except URLError, TimeoutError, OSError:
            pass
        time.sleep(0.3)
    raise ValueError("Startup timed out. Check database access and the private .cache/dev/ logs.")


def run(args):
    node, _ = tools()
    if not PYTHON.is_file():
        raise ValueError("Run py -3.15 scripts/dev.py setup first.")
    entry = frontend_entry()
    if args.api_port == args.web_port:
        raise ValueError("API and web ports must be different.")
    available(args.api_port)
    available(args.web_port)
    env = os.environ.copy()
    env.update(INCIDENTIQ_ENV="development", INCIDENTIQ_READY="true")
    if args.basic:
        env.update(INCIDENTIQ_STORAGE="memory", INCIDENTIQ_AUTH_ENABLED="false")
    else:
        probe = subprocess.run(
            [
                str(PYTHON),
                "-c",
                "import json;from incidentiq.config import load_settings;"
                "s=load_settings();print(json.dumps({'full':s.persistent and s.auth_enabled,"
                "'registry':str(s.token_registry)}))",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if probe.returncode:
            raise ValueError(
                "API configuration is invalid. See docs/quickstart.md; credentials are not printed."
            )
        config = json.loads(probe.stdout)
        if not config["full"] or not Path(config["registry"]).is_file():
            raise ValueError(
                "Full mode needs authenticated PostgreSQL and local tokens. "
                "See docs/quickstart.md, or use --basic."
            )
    api = f"http://127.0.0.1:{args.api_port}"
    web = f"http://127.0.0.1:{args.web_port}"
    web_env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    web_env.update(
        BACKEND_URL=api,
        INCIDENTIQ_AUTH_ENABLED="false" if args.basic else "true",
        NODE_ENV="production",
        HOSTNAME="127.0.0.1",
        PORT=str(args.web_port),
    )
    children, files = [], []
    LOGS.mkdir(parents=True, exist_ok=True)
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    try:
        for name, command, child_env, cwd, url in [
            (
                "api",
                [
                    str(PYTHON),
                    "-m",
                    "uvicorn",
                    "incidentiq.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.api_port),
                    "--no-access-log",
                ],
                env,
                ROOT,
                api + "/health/ready",
            ),
            ("web", [node, str(entry)], web_env, entry.parent, web),
        ]:
            log = (LOGS / f"{name}.log").open("w", encoding="utf-8")
            files.append(log)
            child = subprocess.Popen(
                command, cwd=cwd, env=child_env, stdout=log, stderr=log, **options
            )
            children.append(child)
            wait_ready(url, children)
            print(f"{name} ready: {url}", flush=True)
        print(
            "Basic incident-only demo." if args.basic else "Full authenticated workspace.",
            flush=True,
        )
        print(f"Open {web} | API docs: {api}/docs | Logs: .cache/dev/", flush=True)
        if args.check:
            print("PASS: both services started and answered HTTP; shutting down.")
            return
        print("Press Ctrl+C here to stop both services.", flush=True)
        while True:
            if any(child.poll() is not None for child in children):
                raise ValueError(
                    "A service stopped; both services are being shut down. Check .cache/dev/."
                )
            time.sleep(0.5)
    finally:
        for child in reversed(children):
            stop(child)
        for log in files:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("setup")
    commands.add_parser("configure", help="Rebase copied private configuration for this checkout")
    token = commands.add_parser("token", help="Issue a local token for an existing tenant")
    token.add_argument("--tenant-id", required=True)
    serve = commands.add_parser("run")
    serve.add_argument(
        "--basic", action="store_true", help="Incident CRUD only; no database, login or paid calls"
    )
    serve.add_argument("--api-port", type=int, default=8000)
    serve.add_argument("--web-port", type=int, default=3000)
    serve.add_argument(
        "--check", action="store_true", help="Start, verify HTTP, then stop both services"
    )
    args = parser.parse_args()
    if args.operation == "setup":
        setup()
    elif args.operation == "configure":
        subprocess.run([str(PYTHON), "-m", "scripts.configure_local"], cwd=ROOT, check=True)
    elif args.operation == "token":
        from uuid import UUID

        subprocess.run(
            [
                str(PYTHON),
                "-m",
                "scripts.access_admin",
                "issue",
                "--tenant-id",
                str(UUID(args.tenant_id)),
            ],
            cwd=ROOT,
            check=True,
        )
    else:
        run(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped local services.")
    except ValueError as error:
        print(str(error))
        raise SystemExit(1) from None
    except Exception:
        print("Local setup/start failed. See docs/quickstart.md and .cache/dev/.")
        raise SystemExit(1) from None
