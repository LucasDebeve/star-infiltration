"""Enchaînements entre écrans (menu, campagne, générique, mission) : un seul endroit, pour que la pile de scènes reste cohérente.

Les imports sont faits à l'appel : ces scènes se connaissent entre elles (le jeu ouvre les résultats, les résultats
renvoient à la campagne...), et des imports en tête de fichier feraient une boucle.
"""

from __future__ import annotations


def open_main_menu(game) -> None:
    from game.scenes.main_menu import MainMenuScene

    game.scenes.clear()
    game.scenes.push(MainMenuScene(game))


def open_campaign(game, mission=None) -> None:
    """Menu principal puis carte de la campagne par-dessus (Échap ramène au menu). `mission` : celle à sélectionner."""
    from game.scenes.campaign_scene import CampaignScene
    from game.scenes.main_menu import MainMenuScene

    game.scenes.clear()
    game.scenes.push(MainMenuScene(game))
    game.scenes.push(CampaignScene(game, mission))


def launch_mission(game, mission) -> None:
    """Lance une mission : le générique d'abord (qui lance la partie quand il se termine ou qu'on le passe)."""
    from game.scenes.crawl_scene import CrawlScene

    game.scenes.push(CrawlScene(game, mission))


def start_play(game, mission) -> None:
    """Remplace le générique par la partie."""
    from game.scenes.play_scene import PlayScene

    game.scenes.replace(PlayScene(game, mission.map_path, mission))


def next_mission(game, mission) -> None:
    """Enchaîne sur `mission` (la suivante) en reconstruisant la pile : menu, campagne, générique."""
    open_campaign(game, mission)
    launch_mission(game, mission)
