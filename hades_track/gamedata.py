"""English display names for Hades II internal ids, read from the game's own text files.

The game ships Content/Game/Text/<lang>/*.sjson with `Id` + `DisplayName` pairs for
traits, weapons, aspects, keepsakes, enemies, biomes, vows, and resources. We build a
flat id -> name map once and cache it on disk (the text files only change on patches).
"""

from __future__ import annotations

import json
import os
import pathlib
import re

from . import sjson

CACHE_NAME = "text_en.json"

STEAM_ROOTS = [
    r"C:/Program Files (x86)/Steam/steamapps/common",
    r"C:/Program Files/Steam/steamapps/common",
    r"D:/SteamLibrary/steamapps/common",
    r"E:/SteamLibrary/steamapps/common",
    r"F:/SteamLibrary/steamapps/common",
]


def find_text_dir() -> pathlib.Path | None:
    env = os.environ.get("HADES2_TEXT_DIR")
    if env and pathlib.Path(env).is_dir():
        return pathlib.Path(env)
    for root in STEAM_ROOTS:
        candidate = pathlib.Path(root) / "Hades II" / "Content" / "Game" / "Text" / "en"
        if candidate.is_dir():
            return candidate
    return None


def _flatten(table) -> list[dict]:
    out = []
    values = table.values() if isinstance(table, dict) else table
    for value in values:
        if isinstance(value, dict):
            if "Id" in value:
                out.append(value)
            else:
                out.extend(_flatten(value))
        elif isinstance(value, list):
            out.extend(_flatten(value))
    return out


def build_names(text_dir: pathlib.Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for path in sorted(text_dir.glob("*.sjson")):
        try:
            data = sjson.load_file(path)
        except Exception:
            continue
        for entry in _flatten(data):
            key = entry.get("Id")
            name = entry.get("DisplayName")
            if isinstance(key, str) and isinstance(name, str) and key not in names:
                names[key] = name
    return names


class GameText:
    def __init__(self, cache_dir: pathlib.Path, text_dir: pathlib.Path | None = None):
        self.cache_dir = cache_dir
        self.text_dir = text_dir or find_text_dir()
        self.names: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        cache = self.cache_dir / CACHE_NAME
        if self.text_dir and self.text_dir.is_dir():
            stamp = {
                "dir": str(self.text_dir),
                "mtime": max(p.stat().st_mtime for p in self.text_dir.glob("*.sjson")),
            }
            if cache.is_file():
                try:
                    cached = json.loads(cache.read_text(encoding="utf-8"))
                    if cached.get("stamp") == stamp:
                        self.names = cached["names"]
                        return
                except Exception:
                    pass
            self.names = build_names(self.text_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"stamp": stamp, "names": self.names}, ensure_ascii=False),
                encoding="utf-8",
            )
        elif cache.is_file():
            try:
                self.names = json.loads(cache.read_text(encoding="utf-8"))["names"]
            except Exception:
                self.names = {}

    def has(self, key: str) -> bool:
        return key in self.names

    def name(self, key: str | None, default: str | None = None) -> str:
        if not key:
            return default or "—"
        if key in self.names:
            return _clean(self.names[key])
        base = key.split("_")[0]
        if base in self.names:
            return _clean(self.names[base])
        return default if default is not None else _humanize(key)

    def name_or_none(self, key: str | None) -> str | None:
        if key and key in self.names:
            return _clean(self.names[key])
        return None


def _clean(text: str) -> str:
    """Strip inline formatting tokens such as {!Icons.BountySkull} or {#Emph}."""
    return re.sub(r"\{[^{}]*\}", "", text).strip()


def find_scripts_dir(text_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    """Content/Scripts sits next to Content/Game/Text."""
    if text_dir:
        candidate = text_dir.parent.parent.parent / "Scripts"
        if candidate.is_dir():
            return candidate
    env = os.environ.get("HADES2_SCRIPTS_DIR")
    if env and pathlib.Path(env).is_dir():
        return pathlib.Path(env)
    for root in STEAM_ROOTS:
        candidate = pathlib.Path(root) / "Hades II" / "Content" / "Scripts"
        if candidate.is_dir():
            return candidate
    return None


GOD_FILES = {
    "Aphrodite", "Apollo", "Arachne", "Ares", "Artemis", "Athena", "Chaos",
    "Circe", "Demeter", "Dionysus", "Echo", "Hades", "Hephaestus", "Hera",
    "Hermes", "Hestia", "Icarus", "Medea", "Narcissus", "Poseidon", "Selene",
    "Zeus",
}

_TRAIT_KEY_RE = re.compile(r"^\t([A-Za-z0-9_]+)\s*=\s*$", re.MULTILINE)


def build_god_map(scripts_dir: pathlib.Path) -> dict[str, str]:
    """Map trait id -> god, using the per-god TraitData_<God>.lua split."""
    gods: dict[str, str] = {}
    for path in sorted(scripts_dir.glob("TraitData_*.lua")):
        god = path.stem.split("_", 1)[1]
        if god not in GOD_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _TRAIT_KEY_RE.finditer(text):
            gods.setdefault(match.group(1), god)
    return gods


def build_trait_ids(scripts_dir: pathlib.Path) -> set[str]:
    """Every trait id the game defines (used to drop stale ids from old saves)."""
    ids: set[str] = set()
    for path in scripts_dir.glob("TraitData*.lua"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ids.update(_TRAIT_KEY_RE.findall(text))
    return ids


_TRAIT_CACHE: set[str] | None = None


def load_trait_ids(scripts_dir: pathlib.Path | None) -> set[str]:
    global _TRAIT_CACHE
    if _TRAIT_CACHE is None:
        _TRAIT_CACHE = build_trait_ids(scripts_dir) if scripts_dir else set()
    return _TRAIT_CACHE


_GOD_CACHE: dict[str, str] | None = None
_GOD_CACHE_KEY: str | None = None


def load_god_map(scripts_dir: pathlib.Path | None) -> dict[str, str]:
    global _GOD_CACHE, _GOD_CACHE_KEY
    if not scripts_dir or not scripts_dir.is_dir():
        return _GOD_CACHE or {}
    key = str(scripts_dir)
    if _GOD_CACHE is not None and _GOD_CACHE_KEY == key:
        return _GOD_CACHE
    _GOD_CACHE = build_god_map(scripts_dir)
    _GOD_CACHE_KEY = key
    return _GOD_CACHE


def _humanize(key: str) -> str:
    """Fallback for internal ids with no localization (split CamelCase)."""
    out = []
    word = ""
    for ch in key.replace("_", " "):
        if ch.isupper() and word and not word[-1].isupper():
            out.append(word)
            word = ch
        else:
            word += ch
    out.append(word)
    text = " ".join(out).strip()
    return text[:1].upper() + text[1:] if text else key
