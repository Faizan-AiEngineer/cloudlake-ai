import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {
    ".runtime", ".venv", ".git", ".codex", ".agents", ".aws", "node_modules", "dist", ".terraform",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__", ".idea", ".vscode", "spark-warehouse",
}
OUTPUT = ROOT / "PUBLICATION_MANIFEST.json"
LOCAL_FILE_SUFFIXES = {
    ".pyc", ".db", ".db-journal", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".sqlite-wal",
    ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm", ".log", ".tfplan", ".tmp", ".pem", ".key", ".pfx", ".p12",
}


def main():
    entries = []
    for directory, folders, files in os.walk(ROOT):
        folders[:] = [folder for folder in folders if folder not in EXCLUDE]
        for name in files:
            path = Path(directory) / name
            if path == OUTPUT or not path.is_file() or path.is_symlink():
                continue
            if name == ".env" or name.startswith(".env.") and name != ".env.example":
                continue
            if path.suffix.lower() in LOCAL_FILE_SUFFIXES or ".tfstate" in name or name in {".DS_Store", "Thumbs.db"}:
                continue
            payload = path.read_bytes()
            entries.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=len(payload),
                                sha256=hashlib.sha256(payload).hexdigest()))
    sorted_entries = sorted(entries, key=lambda entry: entry["path"])
    OUTPUT.write_text(json.dumps({"files": len(entries), "entries": sorted_entries}, indent=2) + "\n", encoding="utf-8")
    print(f"Hashed {len(entries)} publication files.")


if __name__ == "__main__":
    main()
