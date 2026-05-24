"""
Webnode automation: canonical + legacy config/lock paths (rename phase 2).

- Config: prefer ~/.sprava_vozidel_webnode_config.json, fall back to ~/.toozhub_webnode_config.json
- Writes: always canonical path; after reading legacy, copy to canonical when possible
- Lock: acquire legacy then canonical (fcntl) so old and new script versions exclude each other
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore

WEBNODE_CONFIG_CANON = Path.home() / ".sprava_vozidel_webnode_config.json"
WEBNODE_CONFIG_LEGACY = Path.home() / ".toozhub_webnode_config.json"

WEBNODE_LOCK_LEGACY = Path("/tmp/toozhub_webnode_upload.lock")
WEBNODE_LOCK_CANON = Path("/tmp/sprava_vozidel_webnode_upload.lock")


def webnode_config_read_path() -> Path:
    if WEBNODE_CONFIG_CANON.exists():
        return WEBNODE_CONFIG_CANON
    return WEBNODE_CONFIG_LEGACY


def webnode_config_write_path() -> Path:
    return WEBNODE_CONFIG_CANON


def load_webnode_config_dict() -> Dict[str, Any]:
    """Load JSON config; if loaded from legacy path, mirror raw content to canonical."""
    path = webnode_config_read_path()
    if not path.exists():
        return {}
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    if path == WEBNODE_CONFIG_LEGACY:
        try:
            WEBNODE_CONFIG_CANON.write_text(raw_text, encoding="utf-8")
            WEBNODE_CONFIG_CANON.chmod(0o600)
        except OSError:
            pass
    return data


def save_webnode_config_dict(data: Dict[str, Any]) -> Path:
    """Persist to canonical path only."""
    target = webnode_config_write_path()
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def acquire_webnode_lock_dual() -> Optional[List[int]]:
    """
    Exclusive non-blocking lock on legacy then canonical file.
    Returns list of fds to pass to release, or None if busy.
    """
    if fcntl is None:
        return []
    fds: List[int] = []
    try:
        for lock_path in (WEBNODE_LOCK_LEGACY, WEBNODE_LOCK_CANON):
            fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fds.append(fd)
        if fds:
            os.write(fds[0], str(os.getpid()).encode())
            try:
                os.fsync(fds[0])
            except OSError:
                pass
        return fds
    except (OSError, IOError):
        for fd in fds:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except Exception:
                pass
        return None


def release_webnode_lock_dual(fds: Optional[List[int]]) -> None:
    if not fds:
        return
    if fcntl is None:
        return
    for fd in fds:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except Exception:
            pass
    for lock_path in (WEBNODE_LOCK_LEGACY, WEBNODE_LOCK_CANON):
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass


def webnode_config_help_lines() -> Tuple[str, ...]:
    return (
        f"  Doporučený soubor: {WEBNODE_CONFIG_CANON}",
        f"  Zastaralý alias (stále podporován): {WEBNODE_CONFIG_LEGACY}",
    )
