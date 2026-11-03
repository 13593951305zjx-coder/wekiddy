"""Package source while keeping keys, user recordings and model weights local."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
destination = root.with_suffix(".zip")
excluded = {".venv", "__pycache__", ".pytest_cache", ".gradle", ".git", "build",
            "models", "downloads", "backups", "verification", "logs"}
count = 0
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if set(relative.parts) & excluded or path.name == ".env" or path.suffix == ".pyc":
            continue
        if relative.parts[:2] == ("tools", "ollama"):
            continue
        if "data" in relative.parts and path.name != ".gitkeep":
            continue
        archive.write(path, Path(root.name) / relative)
        count += 1
with ZipFile(destination) as archive:
    invalid = archive.testzip()
    if invalid:
        raise RuntimeError(f"Archive validation failed: {invalid}")
print(f"Saved {count} source files: {destination}")
