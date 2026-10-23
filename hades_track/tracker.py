"""Sync Hades II save files into Obsidian notes."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import pathlib
import sys
import time

from . import config, extract, gamedata, journal, savefile

NOTE_INDEX = "Hades II.md"
LIVE_NOTE = "Current Run.md"


def _atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _write_if_changed(path: pathlib.Path, text: str) -> bool:
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except UnicodeDecodeError:
            pass
    _atomic_write(path, text)
    return True


def choose_save(candidates: list[tuple[int, float, tuple]]) -> tuple:
    """Highest run count wins; ties break on the newer mtime."""
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


class Tracker:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or config.load()
        self.save_dir = pathlib.Path(self.cfg["save_dir"]) if self.cfg.get("save_dir") else config.find_save_dir()
        if not self.save_dir or not self.save_dir.is_dir():
            raise SystemExit("Hades II save folder not found. Set 'save_dir' in config.json.")
        self.profile = config.active_profile(self.save_dir)
        self.runs_dir = config.vault_runs_dir(self.cfg)
        self.text = gamedata.GameText(config.STATE_DIR / "cache")
        self.gods = gamedata.load_god_map(gamedata.find_scripts_dir(self.text.text_dir))
        self.known_traits = gamedata.load_trait_ids(gamedata.find_scripts_dir(self.text.text_dir))
        self.biome_names = {
            letter: self.text.name(biome_id, default=letter)
            for letter, biome_id in extract.BIOME_IDS.items()
        }
        self.state = config.load_state()

    # -- save handling ----------------------------------------------------
    def _save_paths(self) -> tuple[pathlib.Path, pathlib.Path]:
        return (
            self.save_dir / f"Profile{self.profile}.sav",
            self.save_dir / f"Profile{self.profile}_Temp.sav",
        )

    def _read(self, path: pathlib.Path):
        try:
            return path, path.stat(), savefile.parse_file(path)
        except (OSError, savefile.SaveError, ValueError):
            return path, None, None

    def _best_save(self):
        """Pick the freshest consistent state.

        ProfileN.sav is only written at checkpoints (hub entry, exit), while
        ProfileN_Temp.sav is written during runs. Mid-session the Temp copy can be
        several runs ahead, so the file with the highest run count wins; ties go to
        the newer mtime.
        """
        candidates = []
        for path in self._save_paths():
            if not path.is_file():
                continue
            got = self._read(path)
            if got[1] is None:
                continue
            header, _state = got[2]
            candidates.append((int(header.get("runs") or 0), got[1].st_mtime, got))
        if not candidates:
            raise RuntimeError(f"no readable save file in {self.save_dir}")
        return choose_save(candidates)

    def load_run_records(self) -> tuple[list[extract.RunRecord], dict]:
        path, stat, (header, state) = self._best_save()
        mtime = dt.datetime.fromtimestamp(stat.st_mtime)
        records = extract.build_records(
            header, state, self.text, self.gods,
            finished_at=mtime, date_known=True, known_traits=self.known_traits,
        )
        # Only the newest run can be dated reliably (the save was written when it ended).
        for rec in records[:-1]:
            rec.finished_at = None
            rec.date_known = False
        return records, {"path": str(path), "mtime": stat.st_mtime, "header": header}

    # -- writing ----------------------------------------------------------
    def sync(self, force: bool = False) -> dict:
        records, info = self.load_run_records()
        total = max((r.number for r in records), default=0)
        header_runs = int(info["header"].get("runs") or 0)
        total = max(total, header_runs)

        new_notes = []
        for rec in records:
            path = self.runs_dir / f"{journal.note_name(rec.number)}.md"
            if path.exists() and not force:
                continue
            _atomic_write(path, journal.render(rec, total, self.biome_names))
            new_notes.append(path.name)

        index_path = self.runs_dir / NOTE_INDEX
        _write_if_changed(index_path, journal.render_dashboard(records))

        live_written = False
        if self.cfg.get("live_note", True):
            live = self.live_record()
            live_path = self.runs_dir / LIVE_NOTE
            live_written = _write_if_changed(live_path, journal.render_live(live, self.biome_names))

        self.state.update(
            {
                "last_sync": dt.datetime.now().isoformat(timespec="seconds"),
                "profile": self.profile,
                "save": info["path"],
                "runs_seen": total,
                "notes_written": len(new_notes),
            }
        )
        config.save_state(self.state)
        return {
            "runs": total,
            "new_notes": new_notes,
            "live_written": live_written,
            "vault": str(self.runs_dir),
        }

    def live_record(self) -> extract.RunRecord | None:
        main_path, temp_path = self._save_paths()
        if not temp_path.is_file():
            return None
        got = self._read(temp_path)
        if got[2] is None:
            return None
        main = self._read(main_path) if main_path.is_file() else (main_path, None, None)
        # A Temp copy older than the checkpoint save belongs to an earlier session.
        if main[1] is not None and got[1].st_mtime < main[1].st_mtime - 1:
            return None
        header, state = got[2]
        rec = extract.live_snapshot(state, self.text, self.gods, self.known_traits)
        if rec is None:
            return None
        location = header.get("location") or ""
        if location.startswith("Location_Hub"):
            return None
        if sys.platform == "win32" and not game_running():
            return None
        return rec

    def signatures(self) -> tuple:
        """Cheap change detector: mtime + size of every save we care about."""
        sig = []
        for path in self._save_paths():
            try:
                stat = path.stat()
                sig.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                sig.append((str(path), None, None))
        return tuple(sig)


def game_running() -> bool:
    """True when Hades2.exe is in the process list (cheap, ~40 ms)."""
    if sys.platform != "win32":
        return True
    import subprocess

    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Hades2.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return "Hades2.exe" in out


def _single_instance() -> bool:
    """Windows named mutex so two watchers never write the same notes."""
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, "Local\\hades-track-watcher")
    return not (handle and kernel32.GetLastError() == 183)  # ERROR_ALREADY_EXISTS


def log(message: str, verbose: bool = True) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    if verbose:
        print(line)
    try:
        path = config.STATE_DIR / "watcher.log"
        if path.is_file() and path.stat().st_size > 512_000:
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def watch(
    cfg: dict | None = None,
    interval: int | None = None,
    verbose: bool = True,
    exit_with_game: bool = False,
    start_timeout: int = 600,
    exit_grace: float = 12.0,
) -> None:
    if not _single_instance():
        log("another watcher is already running", verbose)
        return
    cfg = cfg or config.load()
    tracker = Tracker(cfg)
    delay = interval or int(cfg.get("poll_seconds") or 15)

    if exit_with_game:
        log(f"waiting for Hades II to start (timeout {start_timeout}s)", verbose)
        deadline = time.time() + start_timeout
        while not game_running():
            if time.time() >= deadline:
                log("Hades II never started; exiting", verbose)
                return
            time.sleep(2)
        log("Hades II is running", verbose)

    log(f"watching {tracker.save_dir} (profile {tracker.profile}) -> {tracker.runs_dir}", verbose)
    log(f"poll every {delay}s", verbose)
    last_sig: tuple | None = None
    last_hash: str | None = None
    missing_since: float | None = None
    while True:
        try:
            # The player can switch save slots; follow the active profile.
            if config.active_profile(tracker.save_dir) != tracker.profile:
                tracker = Tracker(cfg)
                last_sig = None
                log(f"active profile changed -> profile {tracker.profile}", verbose)
            sig = tracker.signatures()
            if sig != last_sig:
                digest = hashlib.sha1(repr(sig).encode()).hexdigest()
                if digest != last_hash:
                    result = tracker.sync()
                    last_hash = digest
                    if result["new_notes"]:
                        log(f"wrote {', '.join(result['new_notes'])}", verbose)
                    elif result["live_written"]:
                        log("live note updated", verbose)
                last_sig = sig

            if exit_with_game:
                if game_running():
                    missing_since = None
                else:
                    if missing_since is None:
                        missing_since = time.time()
                        log("Hades II closed, waiting for the final save", verbose)
                    elif time.time() - missing_since > exit_grace:
                        tracker.sync()  # last chance to catch the exit save
                        log("done; exiting", verbose)
                        return
        except Exception as exc:  # keep the watcher alive across transient errors
            log(f"sync failed: {exc!r}", verbose)
            time.sleep(min(delay, 10))
        time.sleep(min(delay, 5) if exit_with_game else delay)
