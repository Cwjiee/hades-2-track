"""Launcher for Steam launch options (no console window, no cwd dependency).

    pythonw.exe "C:\\...\\hades-track\\scripts\\watch.py" --exit-when-game-closed

Steam starts the game from its install folder, so this file puts the project on
sys.path itself instead of relying on the current working directory.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hades_track.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
