"""
upload_artifacts.py — Bulk-upload vendor artifacts to the TPRM API.

Scans data/artifacts for supported files (.pdf, .docx, .txt) and
POSTs each one to the /artifacts/upload endpoint.

Usage:
    python scripts/upload_artifacts.py
"""

import sys
from pathlib import Path

import requests

# ── Configuration ────────────────────────────────────────────────
API_URL = "http://127.0.0.1:8000/artifacts/upload"
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "data" / "artifacts"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def upload_file(filepath: Path) -> bool:
    """Upload a single file to the API. Returns True on success."""
    print(f"Uploading {filepath.name}")

    try:
        with open(filepath, "rb") as f:
            response = requests.post(
                API_URL,
                files={"file": (filepath.name, f)},
                timeout=120,
            )
        print(f"  Status: {response.status_code} — {response.text}")
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"  ERROR: {exc}")
        return False


def main() -> None:
    if not ARTIFACTS_DIR.is_dir():
        print(f"Artifacts directory not found: {ARTIFACTS_DIR}")
        sys.exit(1)

    # Collect supported files (skip directories and unsupported types)
    files = sorted(
        p for p in ARTIFACTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    skipped = sum(
        1 for p in ARTIFACTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() not in SUPPORTED_EXTENSIONS
    )
    if skipped:
        print(f"Skipping {skipped} file(s) with unsupported extensions.\n")

    if not files:
        print("No supported artifact files found.")
        sys.exit(0)

    print(f"Found {len(files)} artifact(s) to upload.\n")

    success = 0
    failed = 0

    for filepath in files:
        if upload_file(filepath):
            success += 1
        else:
            failed += 1
        print()  # blank line between uploads

    # ── Summary ──────────────────────────────────────────────────
    print("=" * 40)
    print("Upload Summary")
    print(f"  Total files found : {len(files)}")
    print(f"  Successful        : {success}")
    print(f"  Failed            : {failed}")
    print("=" * 40)


if __name__ == "__main__":
    main()
