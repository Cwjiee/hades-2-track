"""Turn a parsed Hades II save into a journal-friendly run record."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from .gamedata import GameText, load_god_map

# Component prefixes -> primary weapon id (the id that has a localized name).
WEAPON_PREFIXES = [
    ("WeaponStaff", "WeaponStaffSwing"),
    ("WeaponDagger", "WeaponDagger"),
    ("WeaponTorch", "WeaponTorch"),
    ("WeaponAxe", "WeaponAxe"),
    ("WeaponLob", "WeaponLob"),
    ("WeaponSuit", "WeaponSuit"),
]

IGNORED_WEAPON_KEYS = {"WeaponCast", "WeaponBlink", "WeaponSprint"}

BIOME_IDS = {
    "F": "BiomeF",
    "G": "BiomeG",
    "H": "BiomeH",
    "I": "BiomeI",
    "N": "BiomeN",
    "O": "BiomeO",
    "P": "BiomeP",
    "Q": "BiomeQ",
    "C": "BiomeC",
}

RUN_RESULTS = {
    1.0: "victory",
    2.0: "death",
    3.0: "victory",
    4.0: "death",
    5.0: "abandoned",
}


@dataclass
class RunRecord:
    number: int
    outcome: str = "unknown"
    killed_by: str | None = None
    end_room: str | None = None
    end_biome: str | None = None
    duration: float = 0.0
    total_time: float | None = None
    weapon: str | None = None
    aspect: str | None = None
    familiar: str | None = None
    keepsakes: list[str] = field(default_factory=list)
    boons: list[dict] = field(default_factory=list)
    arcana: list[str] = field(default_factory=list)
    vows: list[dict] = field(default_factory=list)
    shrine_points: int = 0
    depth: int | None = None
    biome_route: list[str] = field(default_factory=list)   # biome letters
    rooms: list[dict] = field(default_factory=list)        # {room, encounter, biome}
    damage_taken: float | None = None
    damage_dealt: float | None = None
    damage_taken_by: list[tuple[str, float]] = field(default_factory=list)
    kills: int | None = None
    top_kills: list[tuple[str, float]] = field(default_factory=list)
    resources: dict[str, int] = field(default_factory=dict)
    finished_at: dt.datetime | None = None
    date_known: bool = True

    @property
    def won(self) -> bool:
        return self.outcome == "victory"

    @property
    def duration_text(self) -> str:
        return clock(self.duration)

    @property
    def biome_text(self) -> str:
        return self.end_biome or "—"


def clock(seconds: float | None) -> str:
    if not seconds:
        return "—"
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _letter(room_or_biome: str | None) -> str | None:
    if not room_or_biome:
        return None
    head = room_or_biome.split("_")[0]
    return head if len(head) == 1 and head.isalpha() else None


def _weapon_id(keys) -> str | None:
    for key in keys:
        if key in IGNORED_WEAPON_KEYS:
            continue
        for prefix, weapon in WEAPON_PREFIXES:
            if key.startswith(prefix):
                return weapon
    return None


def _ordered(d: dict) -> list:
    """Return values of a numeric-keyed Lua table in numeric order."""

    def key(item):
        try:
            return float(item[0])
        except (TypeError, ValueError):
            return 0.0

    return [v for _k, v in sorted(d.items(), key=key)]


def _humanize_room(room: str) -> str:
    parts = room.split("_", 1)
    name = parts[1] if len(parts) == 2 else room
    return re.sub(r"\d+$", "", name).replace("_", " ").strip() or room


BOSS_RE = re.compile(r"^(mini)?boss(.+?)(\d*)$", re.IGNORECASE)


def _encounter_label(name: str, text: GameText) -> tuple[str, str | None]:
    """Return (display label, boss name if this is a boss/miniboss encounter)."""
    match = BOSS_RE.match(name)
    if match:
        core = match.group(2)
        boss = text.name_or_none(core) or text.name_or_none(core + "01") or _humanize_boss(core)
        kind = "Miniboss" if match.group(1) else "Boss"
        return f"{kind}: {boss}", boss
    label = text.name_or_none(name) or re.sub(r"(Generated|Encounter|_)+", " ", name)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label).strip(), None


def _humanize_boss(core: str) -> str:
    words = re.findall(r"[A-Z][a-z]+|[A-Z]+(?![a-z])", core) or [core]
    return " ".join(words).strip() or core


def _top_named(counts: dict, text: GameText, n: int, cast=float) -> list[tuple[str, float]]:
    """Aggregate internal ids by display name (several ids can share a name)."""
    merged: dict[str, float] = {}
    for key, value in counts.items():
        if not isinstance(value, (int, float)):
            continue
        merged[text.name(key)] = merged.get(text.name(key), 0.0) + float(value)
    ranked = sorted(merged.items(), key=lambda kv: -kv[1])[:n]
    return [(name, cast(value)) for name, value in ranked]


def build_record(
    number: int,
    raw: dict,
    header: dict,
    text: GameText,
    gods: dict[str, str],
    finished_at: dt.datetime | None = None,
    date_known: bool = True,
    known_traits: set[str] | None = None,
) -> RunRecord:
    rec = RunRecord(number=number, finished_at=finished_at, date_known=date_known)
    rec.outcome = RUN_RESULTS.get(raw.get("RunResult"), "unknown")
    killer = raw.get("KilledByName")
    if killer:
        rec.killed_by = text.name(killer)
        if rec.outcome == "unknown":
            rec.outcome = "death"
    rec.end_room = raw.get("EndingRoomName")
    letter = _letter(rec.end_room)
    if letter:
        rec.end_biome = text.name(BIOME_IDS.get(letter, ""), default=letter)

    rec.duration = float(raw.get("GameplayTime") or 0.0)
    if raw.get("TotalTime"):
        rec.total_time = float(raw["TotalTime"])
    rec.shrine_points = int(raw.get("ShrinePointsCache") or 0)
    if raw.get("RunDepthCache"):
        rec.depth = int(raw["RunDepthCache"])

    # --- weapon / aspect -------------------------------------------------
    hero = raw.get("Hero") or {}
    slotted = hero.get("SlottedTraits") or {}
    weapons = list(raw.get("WeaponsCache") or hero.get("Weapons") or {})
    weapon_id = _weapon_id(weapons)
    if weapon_id:
        rec.weapon = text.name(weapon_id)

    # Aspects can leak in from the hub loadout, so prefer one that matches the
    # weapon actually fired during the run.
    aspect_traits = [
        t for t in (raw.get("TraitCache") or {}) if isinstance(t, str) and t.endswith("Aspect")
    ]
    aspect_id = None
    if weapon_id:
        stem = weapon_id.replace("Weapon", "").replace("Swing", "")
        aspect_id = next((a for a in aspect_traits if stem.lower() in a.lower()), None)
    if aspect_id is None and aspect_traits:
        aspect_id = aspect_traits[0]
    if aspect_id is None:
        aspect_id = slotted.get("Aspect")
    if aspect_id:
        rec.aspect = text.name(aspect_id)
    familiar = slotted.get("Familiar")
    if familiar:
        rec.familiar = text.name(familiar)

    # --- keepsakes -------------------------------------------------------
    for keepsake in _ordered(raw.get("KeepsakeCache") or {}):
        if isinstance(keepsake, str):
            rec.keepsakes.append(text.name(keepsake))

    # --- boons / arcana --------------------------------------------------
    rarity = raw.get("TraitRarityCache") or {}
    traits = raw.get("PickedTraits") or raw.get("TraitCache") or {}
    for trait in traits:
        if not isinstance(trait, str):
            continue
        low = trait.lower()
        if low.endswith("metaupgrade"):
            rec.arcana.append(text.name(trait))
        elif low.endswith("aspect") or low.endswith("keepsake"):
            continue
        elif trait in IGNORED_WEAPON_KEYS or trait.startswith(("Weapon", "Dummy")):
            continue
        else:
            god = gods.get(trait)
            rarity_value = rarity.get(trait)
            if not god and rarity_value == "Duo":
                god = "Duo"
            # Keep real boons only: they either belong to a god, are duo/legendary,
            # or are explicitly named as boons. Room-reward placeholders and other
            # bookkeeping traits otherwise leak in from old saves.
            if not god and rarity_value not in ("Duo", "Legendary") and not trait.endswith("Boon"):
                continue
            rec.boons.append(
                {
                    "name": text.name(trait),
                    "rarity": rarity_value,
                    "god": god,
                    "id": trait,
                }
            )

    # --- vows ------------------------------------------------------------
    for vow, rank in (raw.get("ShrineUpgradesCache") or {}).items():
        try:
            level = int(rank or 0)
        except (TypeError, ValueError):
            level = 0
        if level > 0:
            rec.vows.append({"name": text.name(vow), "rank": level})

    # --- route -----------------------------------------------------------
    for letter in _ordered(raw.get("BiomeVisitOrder") or {}):
        if isinstance(letter, str) and letter not in rec.biome_route:
            rec.biome_route.append(letter)

    for room in _ordered(raw.get("RoomHistory") or {}):
        if not isinstance(room, dict):
            continue
        name = room.get("Name") or ""
        encounter = (room.get("Encounter") or {}).get("Name")
        label, boss = _encounter_label(encounter, text) if encounter else (None, None)
        rec.rooms.append(
            {
                "room": name,
                "label": _humanize_room(name),
                "encounter": label,
                "boss": boss,
                "biome": _letter(name),
            }
        )

    # --- combat ----------------------------------------------------------
    if raw.get("TotalDamageTaken") is not None:
        rec.damage_taken = float(raw["TotalDamageTaken"])
    dealt = raw.get("DamageDealtByHeroRecord") or {}
    if dealt:
        rec.damage_dealt = float(sum(v for v in dealt.values() if isinstance(v, (int, float))))
    taken_by = raw.get("DamageTakenFromRecord") or {}
    rec.damage_taken_by = _top_named(taken_by, text, 5, cast=float)
    kills = raw.get("EnemyKills") or {}
    if kills:
        real_kills = {
            k: v for k, v in kills.items()
            if not re.search(r"(Breakable|Icicle|Rubble|Terrain|Rock)", str(k))
        }
        rec.kills = int(sum(v for v in real_kills.values() if isinstance(v, (int, float))))
        rec.top_kills = _top_named(real_kills, text, 5, cast=int)

    gained = raw.get("ResourcesGained") or {}
    for resource, amount in gained.items():
        if isinstance(amount, (int, float)) and amount:
            if resource in ("Money", "MetaCurrency") or "Ore" in resource or "Essence" in resource:
                rec.resources[text.name(resource)] = int(amount)
    return rec


def build_records(
    header: dict,
    state: dict,
    text: GameText,
    gods: dict[str, str],
    finished_at: dt.datetime | None = None,
    date_known: bool = True,
    known_traits: set[str] | None = None,
) -> list[RunRecord]:
    history = (state.get("GameState") or {}).get("RunHistory") or {}
    records = []
    for key, raw in history.items():
        try:
            number = int(float(key))
        except (TypeError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        records.append(
            build_record(
                number, raw, header, text, gods, finished_at, date_known, known_traits
            )
        )
    records.sort(key=lambda r: r.number)
    return records


def live_snapshot(
    state: dict, text: GameText, gods: dict[str, str], known_traits: set[str] | None = None
) -> RunRecord | None:
    """Describe the run currently in memory (from Profile_Temp.sav)."""
    raw = state.get("CurrentRun") or {}
    if not raw or not raw.get("GameplayTime"):
        return None
    header_runs = int((state.get("GameState") or {}).get("CompletedRunsCache") or 0)
    rec = build_record(header_runs + 1, raw, {}, text, gods, None, True, known_traits)
    rec.date_known = False
    return rec
