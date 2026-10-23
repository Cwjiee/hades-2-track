import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hades_track.tracker import choose_save  # noqa: E402


class ChooseSaveTest(unittest.TestCase):
    """Regression: mid-session the checkpoint save lags behind the Temp save."""

    def test_more_runs_wins_even_when_older(self):
        checkpoint = ("Profile1.sav", 1000.0, ({"runs": 51}, {}))
        temp = ("Profile1_Temp.sav", 900.0, ({"runs": 52}, {}))
        got = choose_save([(51, checkpoint[1], checkpoint), (52, temp[1], temp)])
        self.assertEqual(got[0], "Profile1_Temp.sav")

    def test_newer_mtime_breaks_ties(self):
        old = ("Profile1.sav", 1000.0, ({"runs": 52}, {}))
        new = ("Profile1_Temp.sav", 1100.0, ({"runs": 52}, {}))
        got = choose_save([(52, old[1], old), (52, new[1], new)])
        self.assertEqual(got[0], "Profile1_Temp.sav")

    def test_checkpoint_wins_when_it_is_ahead(self):
        checkpoint = ("Profile1.sav", 1200.0, ({"runs": 53}, {}))
        temp = ("Profile1_Temp.sav", 1100.0, ({"runs": 52}, {}))
        got = choose_save([(53, checkpoint[1], checkpoint), (52, temp[1], temp)])
        self.assertEqual(got[0], "Profile1.sav")


if __name__ == "__main__":
    unittest.main()
