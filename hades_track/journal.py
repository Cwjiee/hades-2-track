"""Render run records as Obsidian markdown notes."""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from .extract import RunRecord

OUTCOME_LABEL = {
    "victory": "Victory",
    "death": "Defeat",
    "abandoned": "Abandoned",
    "unknown": "Unknown",
}

GOOD_GODS = [
    "Apollo", "Aphrodite", "Ares", "Artemis", "Athena", "Chaos", "Demeter",
    "Dionysus", "Hephaestus", "Hera", "Hermes", "Hestia", "Poseidon", "Selene", "Zeus",
]


def note_name(number: int) -> str:
    return f"Run {number:03d}"


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds or 0))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _yaml(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_yaml(v) for v in value) + "]"
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def _rarity(value: str | None) -> str:
    return value or "—"


def frontmatter(rec: RunRecord, base: str) -> str:
    lines = [
        "---",
        "type: hades2-run",
        f"run: {rec.number}",
        f"outcome: {rec.outcome}",
        f"won: {_yaml(rec.won)}",
    ]
    if rec.weapon:
        lines.append(f"weapon: {_yaml(rec.weapon)}")
    if rec.aspect:
        lines.append(f"aspect: {_yaml(rec.aspect)}")
    if rec.killed_by:
        lines.append(f"killed_by: {_yaml(rec.killed_by)}")
    if rec.end_biome:
        lines.append(f"last_biome: {_yaml(rec.end_biome)}")
    lines.append(f"duration: {_yaml(_fmt_duration(rec.duration))}")
    lines.append(f"duration_min: {round((rec.duration or 0) / 60, 1)}")
    if rec.depth:
        lines.append(f"depth: {rec.depth}")
    lines.append(f"vows: {len(rec.vows)}")
    if rec.kills is not None:
        lines.append(f"kills: {rec.kills}")
    if rec.damage_taken is not None:
        lines.append(f"damage_taken: {int(rec.damage_taken)}")
    if rec.finished_at and rec.date_known:
        lines.append(f"date: {rec.finished_at:%Y-%m-%d}")
        lines.append(f"finished: {rec.finished_at:%Y-%m-%dT%H:%M}")
    lines.append("tags: [hades2/run]")
    lines.append("---")
    return "\n".join(lines) + "\n"


def render(rec: RunRecord, total_runs: int, biome_names: dict[str, str]) -> str:
    label = OUTCOME_LABEL.get(rec.outcome, rec.outcome.title())
    headline = f"# {note_name(rec.number)} — {label}"
    if rec.killed_by and not rec.won:
        headline += f" to {rec.killed_by}"
    elif rec.end_biome:
        headline += f" in {rec.end_biome}"

    parts = [headline, ""]
    sub = [
        f"`{label}`",
        _fmt_duration(rec.duration),
    ]
    if rec.weapon:
        sub.append(rec.weapon + (f" · {rec.aspect}" if rec.aspect else ""))
    parts.append(" · ".join(sub))
    parts.append("")

    # Summary table
    rows = [
        ("Result", _result_text(rec)),
        ("Duration", _fmt_duration(rec.duration)),
    ]
    if rec.weapon:
        rows.append(("Weapon", rec.weapon + (f" — {rec.aspect}" if rec.aspect else "")))
    if rec.biome_route:
        rows.append(("Route", " → ".join(biome_names.get(b, b) for b in rec.biome_route)))
    if rec.keepsakes:
        rows.append(("Keepsakes", " → ".join(rec.keepsakes)))
    if rec.vows:
        rows.append(("Vows", ", ".join(f"{v['name']} ({v['rank']})" for v in rec.vows)))
    elif rec.shrine_points:
        rows.append(("Vows", f"{rec.shrine_points} points"))
    if rec.depth:
        rows.append(("Depth", str(rec.depth)))
    if not rec.date_known:
        rows.append(("Recorded", "imported from save (original date unknown)"))
    parts.append("| | |")
    parts.append("| --- | --- |")
    for key, value in rows:
        parts.append(f"| **{key}** | {value} |")
    parts.append("")

    # Route
    if rec.rooms:
        parts.append("## Route")
        parts.append("")
        by_biome: dict[str | None, list[dict]] = defaultdict(list)
        for room in rec.rooms:
            by_biome[room.get("biome")].append(room)
        for biome, rooms in by_biome.items():
            name = biome_names.get(biome or "", biome or "Other")
            bosses = [r["encounter"] for r in rooms if r.get("boss")]
            line = f"- **{name}** — {len(rooms)} rooms"
            if bosses:
                line += " · " + ", ".join(dict.fromkeys(bosses))
            parts.append(line)
        parts.append("")

    # Boons
    if rec.boons:
        parts.append("## Boons")
        parts.append("")
        grouped: dict[str, list[dict]] = defaultdict(list)
        for boon in rec.boons:
            grouped[boon.get("god") or "Other"].append(boon)

        def god_key(name: str):
            return (GOOD_GODS.index(name) if name in GOOD_GODS else 99, name)

        for god in sorted(grouped, key=god_key):
            items = grouped[god]
            parts.append(f"**{god}** ({len(items)})")
            for boon in items:
                rarity = boon.get("rarity")
                suffix = f" — *{rarity}*" if rarity else ""
                parts.append(f"- {boon['name']}{suffix}")
            parts.append("")

    if rec.arcana:
        parts.append("> [!note]- Arcana cards active")
        for card in sorted(set(rec.arcana)):
            parts.append(f"> - {card}")
        parts.append("")

    # Combat
    combat = []
    if rec.damage_taken is not None:
        combat.append(("Damage taken", f"{int(rec.damage_taken):,}"))
    if rec.damage_dealt:
        combat.append(("Damage dealt", f"{int(rec.damage_dealt):,}"))
    if rec.kills is not None:
        combat.append(("Enemies slain", f"{rec.kills:,}"))
    if combat:
        parts.append("## Combat")
        parts.append("")
        parts.append("| | |")
        parts.append("| --- | --- |")
        for key, value in combat:
            parts.append(f"| {key} | {value} |")
        parts.append("")
    if rec.damage_taken_by:
        parts.append("Worst hits taken:")
        for enemy, amount in rec.damage_taken_by:
            parts.append(f"- {enemy} — {int(amount):,}")
        parts.append("")
    if rec.top_kills:
        parts.append("Most slain: " + ", ".join(f"{name} ×{int(count)}" for name, count in rec.top_kills))
        parts.append("")

    if rec.resources:
        parts.append("## Loot")
        parts.append("")
        parts.append(" · ".join(f"{name}: {amount:,}" for name, amount in rec.resources.items()))
        parts.append("")

    if rec.rooms:
        bosses = [r for r in rec.rooms if r.get("boss")]
        if bosses:
            parts.append("## Bosses faced")
            parts.append("")
            for room in bosses:
                where = biome_names.get(room.get("biome") or "", "")
                parts.append(f"- {room['encounter']}" + (f" — {where}" if where else ""))
            parts.append("")

    # Navigation
    nav = [f"[[Hades II]]"]
    if rec.number > 1:
        nav.append(f"[[{note_name(rec.number - 1)}|← previous]]")
    if rec.number < total_runs:
        nav.append(f"[[{note_name(rec.number + 1)}|next →]]")
    parts.append("---")
    parts.append(" · ".join(nav))
    parts.append("")
    return frontmatter(rec, "") + "\n".join(parts)


def _result_text(rec: RunRecord) -> str:
    if rec.won:
        return "**Cleared**" + (f" — {rec.end_biome}" if rec.end_biome else "")
    if rec.outcome == "abandoned":
        return "Abandoned" + (f" in {rec.end_biome}" if rec.end_biome else "")
    if rec.killed_by:
        return f"Slain by **{rec.killed_by}**" + (f" in {rec.end_biome}" if rec.end_biome else "")
    return OUTCOME_LABEL.get(rec.outcome, rec.outcome.title())


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def render_dashboard(records: list[RunRecord], vault_stats: dict | None = None) -> str:
    total = len(records)
    wins = [r for r in records if r.won]
    win_rate = (len(wins) / total * 100) if total else 0.0
    fastest = min(wins, key=lambda r: r.duration) if wins else None
    deepest = max(records, key=lambda r: r.depth or 0) if records else None

    parts = [
        "---",
        "type: hades2-dashboard",
        "tags: [hades2]",
        "---",
        "",
        "# Hades II — Run Journal",
        "",
        "Auto-generated from the game's own save file. Do not edit the tables by hand;",
        "they are rewritten by `hades-track`.",
        "",
        "| Runs | Victories | Win rate | Fastest clear |",
        "| --- | --- | --- | --- |",
        f"| {total} | {len(wins)} | {win_rate:.0f}% | "
        f"{_fmt_duration(fastest.duration) if fastest else '—'} |",
        "",
    ]

    # Per-weapon stats
    per_weapon: dict[str, list[RunRecord]] = defaultdict(list)
    for rec in records:
        per_weapon[rec.weapon or "Unknown"].append(rec)
    if per_weapon:
        parts += ["## Weapons", "", "| Weapon | Runs | Wins | Best time |", "| --- | --- | --- | --- |"]
        for weapon, runs in sorted(per_weapon.items(), key=lambda kv: -len(kv[1])):
            wins_w = [r for r in runs if r.won]
            best = min((r.duration for r in wins_w), default=None)
            parts.append(
                f"| {weapon} | {len(runs)} | {len(wins_w)} | "
                f"{_fmt_duration(best) if best else '—'} |"
            )
        parts.append("")

    # Where runs end
    endings = Counter()
    for rec in records:
        if rec.won:
            endings[f"Cleared — {rec.end_biome}"] += 1
        elif rec.killed_by:
            endings[rec.killed_by] += 1
        elif rec.end_biome:
            endings[rec.end_biome] += 1
    if endings:
        parts += ["## What ends runs", "", "| Cause | Runs |", "| --- | --- |"]
        for cause, count in endings.most_common(12):
            parts.append(f"| {cause} | {count} |")
        parts.append("")

    # Recent runs
    parts += [
        "## Recent runs",
        "",
        "| Run | Result | Weapon | Time | Ended |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rec in sorted(records, key=lambda r: r.number, reverse=True)[:25]:
        result = "Victory" if rec.won else OUTCOME_LABEL.get(rec.outcome, rec.outcome.title())
        ended = rec.killed_by or rec.end_biome or "—"
        link = f"[[{note_name(rec.number)}|{rec.number}]]"
        parts.append(
            f"| {link} | {result} | {rec.weapon or '—'} | {_fmt_duration(rec.duration)} | {ended} |"
        )
    parts.append("")
    parts.append(f"_Last updated {dt.datetime.now():%Y-%m-%d %H:%M}_")
    parts.append("")
    return "\n".join(parts)


def render_live(rec: RunRecord | None, biome_names: dict[str, str]) -> str:
    if rec is None:
        return (
            "---\ntype: hades2-live\ntags: [hades2/live]\n---\n\n"
            "# No run in progress\n\n"
            "This note updates automatically while a run is being played.\n"
        )
    parts = [
        "---",
        "type: hades2-live",
        "tags: [hades2/live]",
        f"run: {rec.number}",
        f"weapon: {_yaml(rec.weapon)}",
        f"duration: {_yaml(_fmt_duration(rec.duration))}",
        "---",
        "",
        f"# Run {rec.number} — in progress",
        "",
        f"`{_fmt_duration(rec.duration)}` · {rec.weapon or 'Unknown weapon'}"
        + (f" · {rec.aspect}" if rec.aspect else ""),
        "",
    ]
    if rec.biome_route:
        parts.append("Route so far: " + " → ".join(biome_names.get(b, b) for b in rec.biome_route))
        parts.append("")
    if rec.keepsakes:
        parts.append("Keepsakes: " + " → ".join(rec.keepsakes))
        parts.append("")
    if rec.boons:
        parts.append("## Boons so far")
        parts.append("")
        for boon in rec.boons:
            parts.append(f"- {boon['name']}" + (f" — *{boon['rarity']}*" if boon.get("rarity") else ""))
        parts.append("")
    parts.append(f"_Snapshot {dt.datetime.now():%H:%M:%S} — the game only writes saves at chamber transitions._")
    parts.append("")
    return "\n".join(parts)
