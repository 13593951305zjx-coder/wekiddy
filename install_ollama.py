"""Install the official portable Ollama CPU runtime inside this project."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "https://api.github.com/repos/ollama/ollama/releases/assets/638733315"
# Pinned official release: the final ZIP region contains the CLI, CPU libraries
# and licenses. Its much larger CUDA libraries precede this region.
ARCHIVE_SIZE = 1469916992
SLICE_START = 1431636829
SLICE_SIZE = ARCHIVE_SIZE - SLICE_START


def runtime_ready(target: Path) -> bool:
    try:
        manifest = json.loads((target / "runtime-installed.json").read_text(encoding="utf-8"))
        return manifest["asset"] == "638733315" and bool(manifest["files"]) and all(
            (target / name).is_file() and (target / name).stat().st_size == size
            for name, size in manifest["files"].items()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


class ArchiveSlice(io.RawIOBase):
    """Expose a downloaded ZIP region at its original archive offsets."""

    def __init__(self, path: Path):
        self.file = path.open("rb")
        self.position = ARCHIVE_SIZE

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (self.position if whence == 1 else ARCHIVE_SIZE if whence == 2 else 0)
        return self.position

    def read(self, size=-1):
        if self.position < SLICE_START:
            raise OSError("Requested a file outside the CPU runtime region")
        self.file.seek(self.position - SLICE_START)
        data = self.file.read(size)
        self.position += len(data)
        return data

    def close(self):
        self.file.close()
        super().close()


def download_runtime() -> Path:
    downloads = ROOT / "downloads"
    downloads.mkdir(exist_ok=True)
    archive = downloads / "ollama-runtime-tail.zip.part"
    offset = archive.stat().st_size if archive.exists() else 0
    if offset == SLICE_SIZE:
        return archive
    if offset > SLICE_SIZE:
        raise RuntimeError("Unexpected runtime download size. Rename downloads/ollama-runtime-tail.zip.part and retry.")
    print("Downloading the official portable runtime (37 MB, CPU inference)...", flush=True)
    request = urllib.request.Request(URL, headers={
        "User-Agent": "AudioInsight-Setup", "Accept": "application/octet-stream",
        "Range": f"bytes={SLICE_START + offset}-{ARCHIVE_SIZE - 1}",
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        expected = f"bytes {SLICE_START + offset}-{ARCHIVE_SIZE - 1}/{ARCHIVE_SIZE}"
        if response.status != 206 or response.headers.get("Content-Range") != expected:
            raise RuntimeError("The download server did not return the requested official ZIP region. Retry setup.")
        last = 0
        with archive.open("ab" if offset else "wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                offset += len(block)
                if time.monotonic() - last > 3:
                    print(f"Downloaded {offset // 1048576} / {SLICE_SIZE // 1048576} MB", flush=True)
                    last = time.monotonic()
    if archive.stat().st_size != SLICE_SIZE:
        raise RuntimeError("Download incomplete. Run install_ollama.cmd again to resume.")
    return archive


def main():
    if os.name != "nt":
        raise RuntimeError("This portable package is for Windows x64.")
    target = ROOT / "tools" / "ollama"
    if not runtime_ready(target):
        archive = download_runtime()
        target.mkdir(parents=True, exist_ok=True)
        files = {}
        with ArchiveSlice(archive) as region, zipfile.ZipFile(region) as package:
            for member in package.infolist():
                if member.is_dir() or member.header_offset < SLICE_START:
                    continue
                if "/cuda_" in member.filename or "/vulkan/" in member.filename:
                    continue
                destination = (target / member.filename).resolve()
                if not destination.is_relative_to(target.resolve()):
                    raise RuntimeError("Invalid archive path")
                files[member.filename] = member.file_size
                # Reuse intact files if a previous extraction was interrupted.
                valid = False
                if destination.is_file() and destination.stat().st_size == member.file_size:
                    checksum = 0
                    with destination.open("rb") as existing:
                        while block := existing.read(1024 * 1024):
                            checksum = zlib.crc32(block, checksum)
                    valid = checksum == member.CRC
                if not valid:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_name(destination.name + ".installing")
                    # Reading the entire member also validates its ZIP CRC.
                    with package.open(member) as source, temporary.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    temporary.replace(destination)
        if "ollama.exe" not in files or "lib/ollama/libllama.dll" not in files:
            raise RuntimeError("The package did not contain the required runtime files")
        marker = target / "runtime-installed.json"
        temporary_marker = marker.with_suffix(".tmp")
        temporary_marker.write_text(json.dumps({"asset": "638733315", "files": files}), encoding="utf-8")
        temporary_marker.replace(marker)
    print("Ollama runtime is ready. Preparing the local text model...", flush=True)
    return subprocess.call([sys.executable, str(ROOT / "bootstrap.py"), "--mode", "local", "--no-browser", "--check"], cwd=ROOT)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Setup stopped. Downloaded files are kept for the next attempt.")
        raise SystemExit(1)
    except Exception as exc:
        print(f"Setup incomplete: {exc}\nCheck the connection and run install_ollama.cmd again.", flush=True)
        raise SystemExit(1)
