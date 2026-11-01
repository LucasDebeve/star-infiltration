"""Interactions du joueur avec le monde : portes, terminaux, sortie, et ramassage des objets.

Un « interactable » est tout objet qui expose :
    reach        distance (px) à laquelle on peut l'actionner
    hold_time    secondes à maintenir la touche (0 = un simple appui)
    anchor       point monde où afficher l'invite
    distance_to(point) -> float
    prompt(inventory) -> Prompt | None     (None = rien à faire pour l'instant)
    interact(ctx)

Le système choisit le plus proche à portée, gère l'appui / le maintien, et signale ce qui se passe
par l'`EventBus` (`interaction_denied`, `item_picked`, ...), sans rien savoir de l'affichage.
Entièrement pur : les tests le pilotent avec `pressed` / `held`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pygame

from game.settings import PICKUP_RADIUS


@dataclass(frozen=True)
class Prompt:
    label: str
    enabled: bool = True  # faux : on voit l'invite, mais l'action est refusée (ex. badge manquant)


@dataclass
class InteractionContext:
    tilemap: object
    inventory: object
    events: object


class Interactable(Protocol):
    reach: float
    hold_time: float
    anchor: pygame.Vector2

    def distance_to(self, point: pygame.Vector2) -> float: ...

    def prompt(self, inventory) -> Prompt | None: ...

    def interact(self, ctx: InteractionContext) -> None: ...


class InteractionSystem:
    def __init__(self, events) -> None:
        self.events = events
        self.target: Interactable | None = None
        self.prompt: Prompt | None = None
        self._held = 0.0

    @property
    def progress(self) -> float:
        """Avancement (0..1) d'une action à maintenir ; 0 s'il n'y en a pas."""
        if self.target is None or self.target.hold_time <= 0:
            return 0.0
        return min(1.0, self._held / self.target.hold_time)

    def reset(self) -> None:
        self.target, self.prompt, self._held = None, None, 0.0

    def update(self, dt: float, pos: pygame.Vector2, tilemap, inventory, interactables, *, pressed: bool, held: bool) -> None:
        """`pressed` : la touche vient d'être appuyée cette image ; `held` : elle est maintenue."""
        target, prompt = self._nearest(pos, inventory, interactables)
        if target is not self.target:
            self._held = 0.0  # on change de cible : l'action en cours est perdue
        self.target, self.prompt = target, prompt
        if target is None:
            self._held = 0.0
            return

        ctx = InteractionContext(tilemap, inventory, self.events)
        if not prompt.enabled:
            self._held = 0.0
            if pressed:
                self.events.emit("interaction_denied", message=prompt.label)
        elif target.hold_time <= 0:
            if pressed:
                target.interact(ctx)
        elif held:
            self._held += dt
            if self._held >= target.hold_time:
                self._held = 0.0
                target.interact(ctx)
        else:
            self._held = 0.0

    @staticmethod
    def _nearest(pos, inventory, interactables):
        best, best_prompt, best_dist = None, None, float("inf")
        for obj in interactables:
            dist = obj.distance_to(pos)
            if dist > obj.reach or dist >= best_dist:
                continue
            prompt = obj.prompt(inventory)
            if prompt is not None:
                best, best_prompt, best_dist = obj, prompt, dist
        return best, best_prompt


def collect_pickups(pos: pygame.Vector2, inventory, pickups: list, events) -> None:
    """Ramasse (et retire de `pickups`) les objets à portée de `pos`."""
    for pickup in [p for p in pickups if p.pos.distance_to(pos) <= PICKUP_RADIUS]:
        pickups.remove(pickup)
        inventory.add(pickup.item)
        events.emit("item_picked", item=pickup.item)
