"""Command line entry point: python -m hades_track <command>."""

from __future__ import annotations

import argparse
import json
import sys

from . import config, journal, tracker


def cmd_init(args) -> int:
    cfg = config.load()
    if args.vault:
        cfg["vault"] = args.vault
    if args.folder:
        cfg["folder"] = args.folder
    if args.save_dir:
        cfg["save_dir"] = args.save_dir
    if args.poll:
        cfg["poll_seconds"] = args.poll
    if not cfg.get("vault"):
        print("could not find an Obsidian vault; pass --vault PATH")
        return 2
    path = config.save(cfg)
    print(f"wrote {path}")
    print(f"vault: {cfg['vault']}")
    print(f"runs folder: {config.vault_runs_dir(cfg)}")
    save_dir = config.find_save_dir()
    print(f"save dir: {cfg.get('save_dir') or save_dir}")
    return 0


def cmd_sync(args) -> int:
    t = tracker.Tracker()
    result = t.sync(force=args.force)
    print(json.dumps(result, indent=2))
    return 0


def cmd_status(args) -> int:
    t = tracker.Tracker()
    records, info = t.load_run_records()
    print(f"save dir : {t.save_dir}")
    print(f"profile  : {t.profile}")
    print(f"save file: {info['path']}")
    print(f"vault    : {t.runs_dir}")
    print(f"runs     : {len(records)} in save, {info['header'].get('runs')} completed")
    existing = len(list(t.runs_dir.glob("Run *.md"))) if t.runs_dir.is_dir() else 0
    print(f"notes    : {existing} run notes on disk")
    live = t.live_record()
    if live:
        print(f"live     : run {live.number} in progress, {journal._fmt_duration(live.duration)}, {live.weapon}")
    else:
        print("live     : idle")
    state = config.load_state()
    if state.get("last_sync"):
        print(f"last sync: {state['last_sync']}")
    print(f"watcher  : {'running' if not tracker._single_instance() else 'not running'}")
    return 0


def cmd_watch(args) -> int:
    tracker.watch(interval=args.interval)
    return 0


def cmd_rebuild(args) -> int:
    """Re-render every note from the save (overwrites generated content)."""
    return cmd_sync(argparse.Namespace(force=True))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hades-track", description="Automatic Hades II run journal for Obsidian")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="write config.json")
    p.add_argument("--vault")
    p.add_argument("--folder")
    p.add_argument("--save-dir")
    p.add_argument("--poll", type=int)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("sync", help="one pass: import any new runs")
    p.add_argument("--force", action="store_true", help="rewrite existing notes")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("rebuild", help="re-render every note from the save")
    p.set_defaults(func=cmd_rebuild)

    p = sub.add_parser("status", help="show what the tracker sees")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("watch", help="poll the save folder forever")
    p.add_argument("--interval", type=int)
    p.set_defaults(func=cmd_watch)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
