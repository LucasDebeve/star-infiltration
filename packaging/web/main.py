"""Point d'entrée de la version web (pygbag : le jeu tourne dans le navigateur, via WebAssembly).

Le navigateur réclame une boucle asynchrone qui lui rend la main à chaque image : c'est `Game.run_async`. Ce fichier est copié
à la racine du paquet web par `packaging/build.py web` ; il n'est pas utilisé autrement.
"""
import asyncio

from game.core.game import Game
from game.scenes.main_menu import MainMenuScene


async def main() -> None:
    game = Game()
    game.scenes.push(MainMenuScene(game))
    await game.run_async()


asyncio.run(main())
