"""Build the two pinned missing Windows/Python 3.15 wheels; no runtime downgrade."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / ".cache/phase5-wheels"


def compiler_environment(vcvars: Path):
    # Passing this command through list2cmdline adds backslashes before CMD quotes.
    # CMD /s removes the outer pair and leaves the batch path's quotes intact.
    command = f'cmd.exe /d /s /c ""{vcvars}" >nul && set"'
    setup = subprocess.check_output(command, text=True)
    environment = dict(os.environ)
    for line in setup.splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            environment[key] = value
    environment["DISTUTILS_USE_SDK"] = "1"
    return environment


def build():
    WHEELS.mkdir(parents=True, exist_ok=True)
    if not list(WHEELS.glob("pyyaml-6.0.3-py3-none-any.whl")):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-binary=PyYAML",
                "--wheel-dir",
                str(WHEELS),
                "PyYAML==6.0.3",
            ],
            env={**os.environ, "PYYAML_FORCE_LIBYAML": "0"},
            check=True,
        )
    if not list(WHEELS.glob("zstandard-0.25.0-cp315-cp315-win_amd64.whl")):
        locator = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / (
            "Microsoft Visual Studio/Installer/vswhere.exe"
        )
        install = subprocess.check_output(
            [
                str(locator),
                "-latest",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            text=True,
        ).strip()
        vcvars = Path(install) / "VC/Auxiliary/Build/vcvars64.bat"
        if not install or not vcvars.is_file():
            raise RuntimeError("Visual Studio C++ tools required for zstandard on Python 3.15")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-binary=zstandard",
                "--wheel-dir",
                str(WHEELS),
                "zstandard==0.25.0",
            ],
            env=compiler_environment(vcvars),
            check=True,
        )
    print("Pinned Python 3.15 compatibility wheels are ready.")


if __name__ == "__main__":
    build()
