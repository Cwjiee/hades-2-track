import unittest


class FakeText:
    """Stand-in for GameText with a fixed id -> name mapping."""

    def __init__(self, names=None):
        self.names = names or {}

    def name(self, key, default=None):
        if not key:
            return default or "—"
        return self.names.get(key, default if default is not None else str(key))

    def name_or_none(self, key):
        return self.names.get(key) if key else None

    def has(self, key):
        return key in self.names


NAMES = {
    "WeaponTorch": "Umbral Flames",
    "WeaponLob": "Argent Skull",
    "TorchDetonateAspect": "Aspect of Moros",
    "ApolloWeaponBoon": "Nova Strike",
    "ApolloCastBoon": "Solar Ring",
    "ForceAresBoonKeepsake": "Sword Hilt",
    "TypoonEye": "Eye of Typhon",
    "TyphonEye": "Eye of Typhon",
    "BiomeF": "Erebus",
    "BiomeI": "Tartarus",
    "BiomeN": "City of Ephyra",
    "BiomeQ": "The Summit",
    "DoorHealMetaUpgrade": "The Wayward Son",
}

FAKE = FakeText(NAMES)


if __name__ == "__main__":
    unittest.main()
