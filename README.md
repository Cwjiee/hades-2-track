# hades-track

Automatic Hades II run journal for an Obsidian vault. It reads the game's own save
file — no mods, no manual entry — and writes one note per run plus a dashboard.

## What it produces

`Games/Hades II/` inside the vault:

- `Run 001.md … Run 0NN.md` — one note per run (outcome, weapon, aspect, route,
  boons by god with rarity, bosses, damage, loot).
- `Hades II.md` — dashboard: win rate, per-weapon record, what ends runs, recent runs.
- `Current Run.md` — live snapshot of the run in progress (updates at every autosave).

## How it works

| Piece | Detail |
| --- | --- |
| Save location | `%USERPROFILE%\Saved Games\Hades II\ProfileN.sav` (active profile read from `activeProfile`) |
| Format | `SGB1` header + adler32 + lz4-compressed [luabins](https://github.com/TannerRogalsky/luabins) Lua state |
| Run data | `GameState.RunHistory` (append-only, one entry per completed run) |
| Live data | `ProfileN_Temp.sav` → `CurrentRun` |
| Names | read from the game's `Content/Game/Text/en/*.sjson` (ids → English display names) |
| God attribution | `Content/Scripts/TraitData_<God>.lua` |
| Trigger | polls mtime/size of the save files; parses only when they change |

Because the game writes `RunHistory` when a run ends, notes appear a few seconds after
you leave the results screen. No game files are modified.

## Setup

```bash
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e .
.venv/Scripts/python.exe -m hades_track.cli init --vault "C:/Users/<you>/Documents/obsidian-vault/main"
```

`init` writes `%LOCALAPPDATA%\hades-track\config.json`. Edit it to change the vault,
subfolder, or poll interval.

Then one of:

```bash
.venv/Scripts/python.exe -m hades_track.cli sync        # import now
.venv/Scripts/python.exe -m hades_track.cli watch       # run forever
scripts\install-autostart.cmd                          # start at login (windowless)
```

## Commands

| Command | Purpose |
| --- | --- |
| `init` | write/update `config.json` |
| `sync` | one pass; writes notes only for runs that don't have one yet |
| `sync --force` | rewrite every note (also `rebuild`) |
| `watch` | poll forever, one instance only |
| `status` | show save/profile/vault/run counts and the live run |

Existing notes are never overwritten unless you pass `--force`, so hand-written notes
at the bottom of a run note survive.

## Backfill behaviour

Runs before the tracker is installed are imported too, but the save has no per-run
timestamp, so those notes carry `Recorded: imported from save (original date unknown)`
and omit `date:`. Everything from the first tracked run onward gets real dates.
Older entries in the save only keep a summary (weapon, biome, boons, killer); the
newest runs carry full detail (route, damage, kills, loot).

## Configuration

`%LOCALAPPDATA%\hades-track\config.json`:

```json
{
  "vault": "C:/Users/jackc/Documents/obsidian-vault/main",
  "folder": "Games/Hades II",
  "save_dir": null,
  "poll_seconds": 15,
  "live_note": true
}
```

`save_dir: null` means auto-detect. Set it if the save folder lives somewhere else.

## Tests

```bash
.venv/Scripts/python.exe -m unittest discover -s tests
```
