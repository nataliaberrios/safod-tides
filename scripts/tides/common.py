from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def load_config(path=None):
    path = Path(path) if path else ROOT / "config.json"
    with path.open() as f:
        return json.load(f)

def sha256_file(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def git_commit(root=ROOT):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None

def provenance_base(script_path, extra=None):
    prov = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "script": str(Path(script_path).resolve()),
        "script_sha256": sha256_file(script_path),
        "git_commit": git_commit(),
        "cwd": os.getcwd(),
    }
    if extra:
        prov.update(extra)
    return prov

def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")

def ensure_output_dir():
    out = ROOT / "outputs" / "tides"
    out.mkdir(parents=True, exist_ok=True)
    return out
