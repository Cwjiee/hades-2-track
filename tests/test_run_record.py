import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import FAKE  # noqa: E402

from hades_track import extract, journal  # noqa: E402

RAW = {
    "RunResult": 2.0,
    "GameplayTime": 615.0,
    "KilledByName": "TyphonEye",
    "EndingRoomName": "Q_Boss01",
    "ShrinePointsCache": 0.0,
    "KeepsakeCache": {"1.0": "ForceAresBoonKeepsake"},
    "TraitCache": {
        "ApolloWeaponBoon": 1.0,
        "TorchDetonateAspect": 1.0,
        "DoorHealMetaUpgrade": 1.0,
    },
    "TraitRarityCache": {"ApolloWeaponBoon": "Epic"},
    "WeaponsCache": {"WeaponLobSpecial": True, "WeaponLob": True, "WeaponCast": True},
    "BiomeVisitOrder": {"1.0": "N", "2.0": "Q"},
    "ShrineUpgradesCache": {"VowOfRivals": 2.0, "VowOfFrenzy": 0.0},
    "DamageTakenFromRecord": {"Prometheus": 100.0, "TyphonEye": 25.0},
    "EnemyKills": {"Crawler": 5.0, "BreakableN": 9.0},
    "Hero": {"SlottedTraits": {"Aspect": "DaggerHomingThrowAspect"}},
    "RoomHistory": {
        "1.0": {"Name": "N_Combat01", "Encounter": {"Name": "GeneratedN"}},
        "2.0": {"Name": "Q_Boss01", "Encounter": {"Name": "BossTyphonEye01"}},
    },
}

GODS = {"ApolloWeaponBoon": "Apollo"}


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.rec = extract.build_record(7, RAW, {}, FAKE, GODS)

    def test_outcome_and_killer(self):
        self.assertEqual(self.rec.outcome, "death")
        self.assertEqual(self.rec.killed_by, "Eye of Typhon")
        self.assertEqual(self.rec.end_biome, "The Summit")

    def test_weapon_and_aspect(self):
        self.assertEqual(self.rec.weapon, "Argent Skull")
        self.assertEqual(self.rec.aspect, "Aspect of Moros")

    def test_boons_grouped_by_god(self):
        names = [b["name"] for b in self.rec.boons]
        self.assertIn("Nova Strike", names)
        # meta upgrades are arcana, not boons
        self.assertNotIn("The Wayward Son", names)
        self.assertIn("The Wayward Son", self.rec.arcana)
        nova = next(b for b in self.rec.boons if b["name"] == "Nova Strike")
        self.assertEqual(nova["god"], "Apollo")
        self.assertEqual(nova["rarity"], "Epic")

    def test_kills_ignore_breakables(self):
        self.assertEqual(self.rec.kills, 5)
        self.assertEqual(self.rec.top_kills, [("Crawler", 5)])

    def test_vows_only_active(self):
        self.assertEqual(self.rec.vows, [{"name": "VowOfRivals", "rank": 2}])

    def test_biome_route_and_rooms(self):
        self.assertEqual(self.rec.biome_route, ["N", "Q"])
        self.assertEqual(self.rec.rooms[-1]["encounter"], "Boss: Eye of Typhon")
        self.assertEqual(self.rec.rooms[-1]["boss"], "Eye of Typhon")

    def test_victory_detection(self):
        raw = dict(RAW, RunResult=1.0, KilledByName=None)
        rec = extract.build_record(9, raw, {}, FAKE, GODS)
        self.assertTrue(rec.won)
        self.assertEqual(rec.outcome, "victory")

    def test_abandoned_detection(self):
        raw = dict(RAW, RunResult=5.0, KilledByName=None)
        rec = extract.build_record(10, raw, {}, FAKE, GODS)
        self.assertEqual(rec.outcome, "abandoned")
        self.assertFalse(rec.won)


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.rec = extract.build_record(
            7, RAW, {}, FAKE, GODS, finished_at=dt.datetime(2026, 10, 23, 21, 5), date_known=True
        )
        self.biomes = {"N": "City of Ephyra", "Q": "The Summit"}

    def test_frontmatter_and_body(self):
        text = journal.render(self.rec, 10, self.biomes)
        self.assertTrue(text.startswith("---\ntype: hades2-run\nrun: 7"))
        self.assertIn("outcome: death", text)
        self.assertIn('weapon: "Argent Skull"', text)
        self.assertIn("date: 2026-10-23", text)
        self.assertIn("# Run 007 — Defeat to Eye of Typhon", text)
        self.assertIn("[[Run 006|← previous]]", text)
        self.assertIn("[[Run 008|next →]]", text)
        self.assertIn("Boss: Eye of Typhon", text)

    def test_imported_note_has_no_date(self):
        self.rec.finished_at = None
        self.rec.date_known = False
        text = journal.render(self.rec, 10, self.biomes)
        self.assertNotIn("\ndate:", text)
        self.assertIn("imported from save", text)

    def test_dashboard_totals(self):
        winner = extract.build_record(
            8, dict(RAW, RunResult=1.0, KilledByName=None, GameplayTime=900.0), {}, FAKE, GODS
        )
        text = journal.render_dashboard([self.rec, winner])
        self.assertIn("| 2 | 1 | 50% | 15:00 |", text)
        self.assertIn("| 1 |", text.replace("[[Run 007|7]]", "| 1 |", 1))


if __name__ == "__main__":
    unittest.main()
