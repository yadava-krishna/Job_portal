"""backend/services/nickname_service.py

Procedural, friendly nickname generator for job seekers.
Pattern: adjective_noun (e.g. 'curious_navigator', 'swift_falcon').
"""

from __future__ import annotations

import random

ADJECTIVES = [
    "swift", "clever", "curious", "bold", "bright", "steady", "sharp", "calm",
    "keen", "brave", "vivid", "agile", "patient", "noble", "daring", "eager",
    "gentle", "valiant", "lucid", "grand", "astute", "dynamic", "stalwart",
    "serene", "resilient", "prudent", "buoyant", "radiant", "vibrant", "intrepid",
    "tenacious", "dexterous", "resourceful", "inventive", "visionary", "cordial",
    "diligent", "sagacious", "zealous", "jubilant", "nimble", "adaptable", "fearless"
]

NOUNS = [
    "navigator", "falcon", "compass", "voyager", "pioneer", "falcon", "harbor",
    "beacon", "mariner", "pathfinder", "stewart", "albatross", "phoenix", "star",
    "anchor", "skipper", "captain", "scout", "ranger", "sentinel", "scholar",
    "architect", "artisan", "catalyst", "strider", "pilot", "voyager", "helm",
    "keel", "current", "corsair", "sovereign", "horizon", "aurora", "zenith"
]


def generate_nickname() -> str:
    """Generate a random human-readable procedural nickname."""
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adj}_{noun}"
