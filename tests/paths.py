"""Chemins des cartes utilisées par les tests."""

from pathlib import Path

# Banc d'essai : une grande carte stable (couloir central, plusieurs salles, 8 gardes, portes à badge, un bouton),
# indépendante des niveaux livrés. Les tests s'y appuient pour des coordonnées précises.
SANDBOX = Path(__file__).parent / "data" / "sandbox.txt"

from game.campaign import load_campaign  # noqa: E402

CAMPAIGN = load_campaign()
TRAINING = CAMPAIGN.get("training").map_path
CRUISER = CAMPAIGN.get("cruiser").map_path
BLACKOUT = CAMPAIGN.get("blackout").map_path
