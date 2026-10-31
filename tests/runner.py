"""Joueur virtuel pour les tests : suit des chemins A*, ouvre les portes dont il a le badge, appuie sur les boutons."""
import pygame

from game.core.input import InputState
from game.scenes import play_scene


class Runner:
    """Joueur virtuel : suit des chemins A*, ouvre les portes dont il a le badge, pirate, extrait.

    Il ignore les gardes (supprimés par le test) : il prouve que la mission est jouable de bout en bout.
    """

    def __init__(self, game, scene, monkeypatch) -> None:
        self.game, self.scene, self.tm = game, scene, scene.tilemap
        self.control = {"move": pygame.Vector2(), "interact": False}
        monkeypatch.setattr(
            play_scene, "read_input", lambda: InputState(move=self.control["move"], run=True, interact=self.control["interact"])
        )

    @property
    def tile(self):
        return self.tm.world_to_tile(*self.scene.player.pos)

    def frames(self, count: int) -> None:
        for _ in range(count):
            self.scene.update(1 / 60)

    def walk(self, target) -> None:
        from game.ai.pathfinding import find_path

        path = find_path(self.tm, self.tile, target)
        assert path, f"pas de chemin {self.tile} -> {target}"
        for tx, ty in path[1:]:
            goal = pygame.Vector2((tx + 0.5) * 32, (ty + 0.5) * 32)
            for _ in range(60):
                offset = goal - self.scene.player.pos
                if offset.length() < 5:
                    break
                self.control["move"] = offset.normalize()
                self.frames(1)
            else:
                raise AssertionError(f"bloqué avant {(tx, ty)}")
        self.control["move"] = pygame.Vector2()

    def press(self, button_id: str) -> None:
        """Va sur le bouton et appuie sur E, comme le ferait le joueur."""
        self.go(self.tm.buttons[button_id].tile)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
        self.frames(2)

    def use_terminal(self, action: str = "data", tile=None) -> None:
        """Va au terminal (celui de données par défaut), l'utilise comme le joueur (appui sur E), choisit `action` dans son menu,
        puis attend la fin de la connexion."""
        from game.settings import TERMINAL_JOB_TIME

        if tile is None:
            from game.objectives import STEAL_PLANS, objective_spawns

            spawn = objective_spawns(self.tm, STEAL_PLANS)[0]
            tile = (spawn.tx, spawn.ty)
        self.go(tile)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
        self.frames(2)
        menu = self.game.scenes.current
        assert type(menu).__name__ == "TerminalScene", "le terminal n'a pas ouvert son menu"
        assert menu.choose(action), f"le terminal ne propose pas {action!r}"
        self.frames(int(TERMINAL_JOB_TIME[action] * 60) + 20)

    def take_uniform(self, wear: bool = True) -> None:
        """Fouille le premier casier (E maintenu) et, si `wear`, enfile l'uniforme avec la touche dédiée."""
        from game.core import bindings
        from game.settings import LOCKER_TIME

        spawn = self.tm.spawns_of("uniform")[0]
        self.go((spawn.tx, spawn.ty))
        self.control["interact"] = True
        self.frames(int(LOCKER_TIME * 60) + 20)
        self.control["interact"] = False
        assert self.scene.inventory.has_uniform, "le casier n'a pas livré l'uniforme"
        if wear:
            self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=bindings.current.keys("disguise")[0]))
            self.frames(2)
            assert self.scene.inventory.uniform_worn

    def go(self, target) -> None:
        """Rejoint `target`, en ouvrant au besoin les portes que le badge permet d'ouvrir."""
        from game.ai.pathfinding import find_path
        from game.systems.interaction import InteractionContext

        for _ in range(10):
            if find_path(self.tm, self.tile, target):
                return self.walk(target)
            for door in self.scene.doors:
                prompt = door.prompt(self.scene.inventory)  # ce que le joueur verrait : le badge, ou l'uniforme porté, ouvre la porte
                if door.is_open or prompt is None or not prompt.enabled:
                    continue
                beside = [
                    (x + dx, y + dy)
                    for x, y in door.tiles
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if not self.tm.is_solid(x + dx, y + dy) and find_path(self.tm, self.tile, (x + dx, y + dy))
                ]
                if beside:
                    self.walk(beside[0])
                    door.interact(InteractionContext(self.tm, self.scene.inventory, self.game.events))
                    break
            else:
                raise AssertionError(f"bloqué avant {target} : aucun badge ne permet d'avancer")
        raise AssertionError("trop de portes à franchir")
