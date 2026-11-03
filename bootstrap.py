"""Create/reuse the project environment and start its local web application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "audio_llm_backend"
ENVIRONMENT = BACKEND / ".venv"


def checked_run(arguments: list[str], **kwargs) -> None:
    result = subprocess.run(arguments, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed with exit code {result.returncode}. See the message above.")


def ensure_environment(mode: str) -> Path:
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required. Install Python 3.11 or 3.12 and retry.")
    executable = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        print("Creating the project's Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    requirement_files = [BACKEND / "requirements.txt"]
    imports = ["fastapi", "uvicorn", "dotenv", "openai", "multipart", "opencc"]
    if mode == "local":
        requirement_files.append(BACKEND / "requirements-local.txt")
        imports.extend(["faster_whisper", "librosa", "numpy", "av", "sherpa_onnx"])
    fingerprint = hashlib.sha256(b"\n".join(path.read_bytes() for path in requirement_files)).hexdigest()
    marker = ENVIRONMENT / f".dependencies-{mode}.json"
    try:
        already_installed = json.loads(marker.read_text()).get("sha256") == fingerprint
    except (OSError, ValueError):
        already_installed = False
    check = subprocess.run(
        [str(executable), "-c", "import " + ", ".join(imports)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if not already_installed or check.returncode:
        print("Checking/installing project dependencies. The first setup may take several minutes...", flush=True)
        arguments = [str(executable), "-m", "pip", "install"]
        for requirement in requirement_files:
            arguments.extend(["-r", str(requirement)])
        checked_run(arguments, cwd=BACKEND)
        marker.write_text(json.dumps({"sha256": fingerprint}), encoding="utf-8")
    if not (BACKEND / ".env").exists():
        shutil.copyfile(BACKEND / ".env.example", BACKEND / ".env")
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "cloud", "mock"), default="local")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--lan", action="store_true")
    args = parser.parse_args()
    executable = ensure_environment(args.mode)
    command = [str(executable), str(BACKEND / "launch_web.py"), "--mode", args.mode]
    if args.no_browser:
        command.append("--no-browser")
    if args.lan:
        command.append("--lan")
    if args.check:
        command.append("--check")
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    return subprocess.call(command, cwd=BACKEND, env=environment)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        print(f"Startup failed: {exc}", flush=True)
        raise SystemExit(1)
