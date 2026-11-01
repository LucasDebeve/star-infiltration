"""Astuces contextuelles : de courts messages affichés quand le joueur s'approche de l'endroit où ils servent.

Une carte place des zones d'astuce (directive `@tip x,y -> nom [rayon]`) ; l'entraînement s'en sert pour apprendre les
commandes au bon moment, à la place d'un pense-bête permanent à l'écran. Logique pure : `TipTracker` décide quelle astuce
montrer et quand elle est comprise (action faite, temps écoulé) ; `format_tip` y met les touches réellement utilisées
(clavier remappé, ou boutons de la manette).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from game.core import bindings

DEFAULT_RADIUS = 3.0  # tuiles
FADE_RATE = 4.0  # opacité par seconde
MOVE_DONE = 160.0  # px parcourus pour qu'on estime l'astuce de déplacement comprise


@dataclass(frozen=True)
class Tip:
    id: str
    text: str  # modèle : {move} {run} {crouch} {interact} {throw} {aim} {pause}
    done_on: str | None = None  # événement du jeu qui l'accomplit
    duration: float | None = None  # sinon elle disparaît après ce nombre de secondes affichées
    needs: str | None = None  # "decoy" : seulement si le joueur a un leurre
    done_distance: float | None = None  # ... ou après avoir parcouru cette distance (px)
    done_crouch: float | None = None  # ... ou après être resté accroupi ce temps (s)


TIPS: dict[str, Tip] = {
    tip.id: tip
    for tip in (
        Tip("move", "Déplacez-vous avec {move}\nCourir (bruyant) : {run}     Pause : {pause}", done_distance=MOVE_DONE),
        Tip("crouch", "Accroupi ({crouch}), vous faites moins de bruit et les gardes vous repèrent moins bien", done_crouch=1.5),
        Tip("pickup", "Marchez sur un objet pour le ramasser", done_on="item_picked"),
        Tip("door", "Approchez-vous d'une porte et appuyez sur {interact} pour l'ouvrir", done_on="door_opened"),
        Tip("badge_door", "Les voyants de la porte indiquent le badge qu'il faut\nMunissez-vous-en, puis appuyez sur {interact}", done_on="door_opened"),
        Tip("button", "Appuyez sur {interact} près du bouton pour ouvrir ou fermer le champ de force", done_on="button_pressed"),
        Tip("guard", "Restez hors du cône de vision du garde\nCachez-vous derrière les caisses, ou passez-le en silence", duration=8.0),
        Tip("decoy", "Lancez un leurre avec {throw} (visez avec {aim}) : le garde ira voir d'où vient le bruit", done_on="decoy_thrown", needs="decoy"),
        Tip("hack", "Appuyez sur {interact} près du terminal, choisissez « Télécharger les données »\npuis restez près de lui le temps de la connexion", done_on="terminal_hacked"),
        Tip("exit", "Rejoignez la zone d'extraction et appuyez sur {interact}", done_on="mission_complete"),
    )
}


@dataclass(frozen=True)
class TipZone:
    tip: str  # clé de `TIPS`
    tile: tuple[int, int]
    radius: float = DEFAULT_RADIUS  # en tuiles


def format_tip(text: str) -> str:
    """Remplace les noms de commandes par les touches (ou boutons) en vigueur."""
    label = bindings.label
    aim = "le joystick droit" if bindings.device == bindings.PAD else "la souris"
    return text.format(
        move=label("move"),
        run=label("run"),
        crouch=label("crouch"),
        interact=label("interact"),
        throw=label("throw"),
        pause=label("pause"),
        aim=aim,
    )


class _State:
    __slots__ = ("done", "shown", "moved", "crouched")

    def __init__(self) -> None:
        self.done = False
        self.shown = 0.0  # secondes affichées
        self.moved = 0.0  # px parcourus pendant l'affichage
        self.crouched = 0.0  # secondes accroupi pendant l'affichage


class TipTracker:
    def __init__(self, zones: list[TipZone], tile_size: int) -> None:
        self.zones = list(zones)
        self.tile_size = tile_size
        self.states = [_State() for _ in self.zones]
        self.active: int | None = None  # indice de la zone dont l'astuce est affichée
        self.shown: int | None = None  # dernière affichée (pour son fondu de sortie)
        self.alpha = 0.0
        self._last_pos: pygame.Vector2 | None = None

    @property
    def current(self) -> tuple[Tip, float] | None:
        """(astuce, opacité 0..1) à dessiner, ou None s'il n'y a rien à montrer."""
        if self.shown is None or self.alpha <= 0:
            return None
        return TIPS[self.zones[self.shown].tip], self.alpha

    def _eligible(self, i: int, pos: pygame.Vector2, has_decoy: bool) -> float | None:
        """Distance (en tuiles) à la zone si son astuce peut s'afficher maintenant, sinon None."""
        zone, tip = self.zones[i], TIPS[self.zones[i].tip]
        if self.states[i].done or (tip.needs == "decoy" and not has_decoy):
            return None
        distance = math.dist(pos, ((zone.tile[0] + 0.5) * self.tile_size, (zone.tile[1] + 0.5) * self.tile_size)) / self.tile_size
        return distance if distance <= zone.radius else None

    def update(self, dt: float, pos, stance_is_crouch: bool = False, has_decoy: bool = False, hidden: bool = False) -> None:
        """`hidden` : on ne montre rien (fin de mission, menu...)."""
        pos = pygame.Vector2(pos)
        step = pos.distance_to(self._last_pos) if self._last_pos is not None else 0.0
        self._last_pos = pos
        best, best_distance = None, None
        if not hidden:
            for i in range(len(self.zones)):
                distance = self._eligible(i, pos, has_decoy)
                if distance is not None and (best is None or distance < best_distance):
                    best, best_distance = i, distance
        self.active = best
        if best is not None:
            self.shown = best
            state, tip = self.states[best], TIPS[self.zones[best].tip]
            state.shown += dt
            state.moved += step
            state.crouched += dt if stance_is_crouch else 0.0
            if (tip.duration is not None and state.shown >= tip.duration) or (tip.done_distance is not None and state.moved >= tip.done_distance) or (tip.done_crouch is not None and state.crouched >= tip.done_crouch):
                state.done = True
                self.active = None
        target = 1.0 if self.active is not None else 0.0
        self.alpha = min(target, self.alpha + FADE_RATE * dt) if target > self.alpha else max(target, self.alpha - FADE_RATE * dt)

    def notify(self, event: str) -> None:
        """Un événement du jeu : l'astuce affichée, si c'est celui qu'elle attendait, est comprise."""
        if self.active is None:
            return
        if TIPS[self.zones[self.active].tip].done_on == event:
            self.states[self.active].done = True
            self.active = None

    def reset(self) -> None:
        self.states = [_State() for _ in self.zones]
        self.active = self.shown = None
        self.alpha = 0.0
        self._last_pos = None
