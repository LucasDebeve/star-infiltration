"""Objectifs de mission : ce que le joueur doit accomplir avant de pouvoir quitter la carte.

Chaque objectif désigne un genre de point de la carte (`tile` : un terminal `T`, une console `C`, un prisonnier `Q`)
et fournit les textes qui l'accompagnent. Logique pure : la scène de jeu y lit ses consignes, `level_check` y lit
quel point rendre atteignable, `campaign` y valide le champ `objective` des missions.

Pour ajouter un objectif : une entrée ici, une entité interactive dans `game/entities/`, une branche dans
`PlayScene.objective_done`, et ses tuiles dans `Tilemap` (voir `FREE_PRISONER`, déjà préparé).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Objective:
    id: str
    label: str  # nom court (carte de la campagne)
    tile: str  # genre de point (`Spawn.kind`) de la carte qui porte l'objectif
    goal: str  # consigne tant que l'objectif n'est pas accompli
    done: str  # notification quand il l'est
    calm: str  # consigne d'extraction, sans alerte
    flee: str  # consigne d'extraction, pendant l'alerte
    missing: str  # invite de la sortie tant que l'objectif n'est pas accompli
    playable: bool = True  # False : le terrain est préparé (tuiles, validation) mais pas encore le gameplay


STEAL_PLANS = Objective(
    "steal_plans",
    "Voler les plans",
    "terminal",
    "Objectif : pirater le terminal pour récupérer les données",
    "Données téléchargées : rejoignez la sortie",
    "Objectif : rejoindre la sortie avec les données",
    "FUITE : rejoignez la sortie !",
    "Données requises",
)
CUT_POWER = Objective(
    "cut_power",
    "Couper l'alimentation",
    "console",
    "Objectif : atteindre la salle de contrôle et couper l'alimentation",
    "Alimentation coupée : rejoignez la sortie dans le noir",
    "Objectif : rejoindre la sortie",
    "FUITE : rejoignez la sortie !",
    "Alimentation active",
)
FREE_PRISONER = Objective(
    "free_prisoner",
    "Libérer un prisonnier",
    "prisoner",
    "Objectif : ouvrir la cellule et libérer le prisonnier",
    "Prisonnier libéré : rejoignez la sortie avec lui",
    "Objectif : rejoindre la sortie avec le prisonnier",
    "FUITE : rejoignez la sortie avec le prisonnier !",
    "Prisonnier à libérer",
)
STEAL_SHIP = Objective(  # la console de la salle de contrôle libère les vaisseaux ; la sortie est le vaisseau volé
    "steal_ship",
    "Voler un vaisseau",
    "console",
    "Objectif : atteindre la salle de contrôle et libérer les vaisseaux",
    "Rayons tracteurs et attaches désactivés : rejoignez le vaisseau",
    "Objectif : rejoindre le vaisseau",
    "FUITE : rejoignez le vaisseau !",
    "Rayons tracteurs actifs",
)

STEAL_UNIFORM = Objective(  # le casier d'un officier : l'uniforme se porte ensuite (touche dédiée) pour passer pour un membre du personnel
    "steal_uniform",
    "Dérober un uniforme",
    "uniform",
    "Objectif : fouiller le casier de l'officier et dérober son uniforme",
    "Uniforme impérial dérobé : rejoignez la sortie",
    "Objectif : rejoindre la sortie avec l'uniforme",
    "FUITE : rejoignez la sortie !",
    "Uniforme à dérober",
)

OBJECTIVES = {o.id: o for o in (STEAL_PLANS, CUT_POWER, FREE_PRISONER, STEAL_SHIP, STEAL_UNIFORM)}
DEFAULT_OBJECTIVE = STEAL_PLANS.id


def get_objective(objective_id: str) -> Objective:
    return OBJECTIVES[objective_id]


def objective_spawns(tilemap, objective: Objective) -> list:
    """Les points de la carte qui portent l'objectif. Pour voler des plans : seulement les terminaux qui savent télécharger
    des données (les autres, qui coupent la lumière ou les caméras, ne sont que des outils)."""
    spawns = tilemap.spawns_of(objective.tile)
    if objective is STEAL_PLANS:
        return [s for s in spawns if tilemap.terminal_spec((s.tx, s.ty)).can("data")]
    return spawns


def infer_objective(tilemap) -> Objective:
    """L'objectif que porte une carte : celui qu'elle déclare (`@objective`), sinon celui dont elle contient le point
    (le vol de plans par défaut). La console `C` sert à deux objectifs : seule la directive les distingue."""
    declared = getattr(tilemap, "declared_objective", None)
    if declared is not None:
        return OBJECTIVES[declared]
    for objective in OBJECTIVES.values():
        if objective.playable and objective_spawns(tilemap, objective):
            return objective
    return STEAL_PLANS
