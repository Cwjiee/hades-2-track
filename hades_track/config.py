"""Configuration + save-file discovery."""

from __future__ import annotations

import json
import os
import pathlib
import struct

from . import savefile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_NAME = "config.json"
STATE_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA") or pathlib.Path.home()) / "hades-track"

DEFAULTS = {
    "vault": None,
    "folder": "Games/Hades II",
    "save_dir": None,
    "poll_seconds": 15,
    "live_note": True,
    "language": "en",
}


def config_path() -> pathlib.Path:
    env = os.environ.get("HADES_TRACK_CONFIG")
    if env:
        return pathlib.Path(env)
    local = PROJECT_ROOT / CONFIG_NAME
    if local.is_file():
        return local
    return STATE_DIR / CONFIG_NAME


def load() -> dict:
    path = config_path()
    cfg = dict(DEFAULTS)
    if path.is_file():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    if not cfg.get("vault"):
        cfg["vault"] = guess_vault()
    return cfg


def save(cfg: dict) -> pathlib.Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


def guess_vault() -> str | None:
    env = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env and pathlib.Path(env).is_dir():
        return env
    home = pathlib.Path.home()
    for candidate in [
        home / "Documents" / "obsidian-vault" / "main",
        home / "Documents" / "Obsidian Vault",
        home / "Documents" / "Obsidian",
    ]:
        if (candidate / ".obsidian").is_dir():
            return str(candidate)
    return None


def find_save_dir() -> pathlib.Path | None:
    env = os.environ.get("HADES2_SAVE_DIR")
    candidates = [pathlib.Path(env)] if env else []
    candidates.append(pathlib.Path.home() / "Saved Games" / "Hades II")
    for cand in candidates:
        if cand and cand.is_dir():
            return cand
    return None


def active_profile(save_dir: pathlib.Path) -> int:
    """activeProfile is `SGB1` + length-prefixed string such as 'Profile1'."""
    path = save_dir / "activeProfile"
    try:
        data = path.read_bytes()
        if data[:4] == savefile.MAGIC:
            length = struct.unpack("<I", data[4:8])[0]
            name = data[8:8 + length].decode("utf-8", "replace")
            if name.lower().startswith("profile") and name[7:].isdigit():
                return int(name[7:])
    except (OSError, struct.error, ValueError):
        pass
    for slot in (1, 2, 3, 4):
        if (save_dir / f"Profile{slot}.sav").is_file():
            return slot
    return 1


def vault_runs_dir(cfg: dict) -> pathlib.Path:
    return pathlib.Path(cfg["vault"]) / cfg["folder"]


def state_file() -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "state.json"


def load_state() -> dict:
    path = state_file()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict) -> None:
    state_file().write_text(json.dumps(state, indent=2), encoding="utf-8")
