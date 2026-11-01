"""Scène de jeu : charge une carte, orchestre joueur, gardes, objets, interactions, caméra et affichage."""

from __future__ import annotations

from pathlib import Path

import pygame

from game import terminals as terminal_actions
from game.ai.guard import Guard, GuardState
from game.core import bindings
from game.core.audio import attenuation
from game.core.camera import Camera
from game.core.input import read_input
from game.core.scene import Scene
from game.dev import DEV_KEYS
from game.difficulty import get_difficulty
from game.entities.decoy import Decoy
from game.entities.door import Door, build_doors
from game.entities.exit_pad import ExitPad
from game.entities.field_button import FieldButton
from game.entities.locker import Locker
from game.entities.pickup import Pickup
from game.entities.player import Player, Stance
from game.entities.power_console import POWER, RELEASE, PowerConsole
from game.entities.prisoner import Prisoner
from game.entities.security_camera import SecurityCamera
from game.entities.terminal import Terminal
from game.items import Inventory, Item, ItemKind
from game.objectives import CUT_POWER, FREE_PRISONER, STEAL_PLANS, STEAL_SHIP, STEAL_UNIFORM, get_objective, infer_objective, objective_spawns
from game.progress import MissionStats, compute_result
from game.scenes.pause_scene import PauseScene
from game.scenes.results_scene import ResultsScene
from game.settings import (
    CAMERA_OFF_TIME,
    CAMERA_RESPONDERS,
    CAMERA_ZOOM,
    CAMERA_ZOOM_EPS,
    CELLS_OPEN_NOISE,
    COLORS,
    DEBUG_KEY,
    DECOY_NOISE,
    DECOY_SIZE,
    FIELD_LIGHT_SPACING,
    FIELD_PENDING_BLINK,
    GUARD_AURA,
    GUARD_FOV,
    GUARD_TORCH,
    GUARD_VISION_RANGE,
    LIGHTING_KEY,
    LIGHTS_OUT_NOISE,
    LIGHTS_OUT_TIME,
    MAX_BADGE_LEVEL,
    PLAYER_LIGHT,
    PRISONER_EXIT_RANGE,
    QUIT_KEY,
    RESTART_KEY,
    SCREEN_SIZE,
    SHAKE_DOOR,
    SHAKE_EVENTS,
    SHAKE_FIELD,
    SHAKE_RANGE,
    SHIP_RELEASE_FADE,
    SPOT_LIGHTS,
    THROW_RANGE,
)
from game.systems.acoustics import Acoustics
from game.systems.alert import AlertSystem
from game.systems.ambience import Ambience, AmbientSource
from game.systems.effects import Effects
from game.systems.interaction import InteractionSystem, collect_pickups
from game.systems.sound_director import SoundDirector
from game.tips import TipTracker, format_tip
from game.ui.backdrop import SpaceLayer
from game.ui.hud import Hud
from game.ui.icons import item_color
from game.ui.lighting import Lighting, lerp_color
from game.ui.world_overlay import WorldOverlay
from game.world.exposure import light_at, visibility_factor, visibility_zone
from game.world.lights import LightSpec
from game.world.raycast import cast_ray
from game.world.tilemap import Tilemap

# Ce que ramasse le joueur, par genre de repère de la carte.
PICKUP_SPAWNS = {"keycard": ItemKind.KEYCARD, "decoy": ItemKind.DECOY}


class PlayScene(Scene):
    pad_context = "game"  # la manette agit sur le jeu (interagir, leurre, pause...), pas sur un menu

    def __init__(self, game, map_path: str | Path, mission=None) -> None:
        """`mission` : la mission de la campagne en cours (ses résultats sont enregistrés) ; None pour une carte seule
        (son objectif est alors déduit de la carte)."""
        super().__init__(game)
        self.map_path = map_path
        self.mission = mission
        self.hud = Hud()
        self.overlay = WorldOverlay(SCREEN_SIZE)
        self.interaction = InteractionSystem(game.events)
        self.director = SoundDirector(game.audio, game.events)
        self.space = SpaceLayer(SCREEN_SIZE)
        self.time = 0.0  # secondes écoulées : anime les champs de force et les étoiles
        self.debug = False
        self._world_buffer: pygame.Surface | None = None  # image du monde avant zoom
        self._start_level()
        self._aim_offset = None
        self._shake_handlers = {  # événements qui font trembler la caméra
            **{name: (lambda amount: lambda **_: self._shake(amount))(amount) for name, amount in SHAKE_EVENTS.items()},
            "door_opened": lambda door, **_: self._shake(SHAKE_DOOR, door.anchor),
            "field_toggled": lambda field, **_: self._shake(SHAKE_FIELD, self._field_center(self.tilemap.fields[field])),
        }
        self._tip_handlers = {  # événements qui font comprendre une astuce (elle ne le sait que si elle est affichée)
            name: (lambda event: lambda **_: self.tips.notify(event))(name) for name in ("item_picked", "door_opened", "button_pressed", "terminal_hacked", "decoy_thrown", "mission_complete")
        }
        self._handlers = {
            "noise": self._on_noise,
            "item_picked": self._on_item_picked,
            "interaction_denied": self._on_denied,
            "terminal_hacked": self._on_terminal_hacked,
            "terminal_opened": self._on_terminal_opened,
            "ships_released": self._on_ships_released,
            "prisoner_freed": self._on_prisoner_freed,
            "uniform_stolen": self._on_uniform_stolen,
            "camera_spotted": self._on_camera_spotted,
            "power_cut": self._on_power_cut,
            "field_toggled": self._on_field_toggled,
            "mission_complete": self._on_mission_complete,
            "decoy_thrown": self._on_decoy_thrown,
            "alert_raised": self._on_alert_raised,
            "reinforcements_arrived": self._on_reinforcements,
            "lockdown": self._on_lockdown,
        }

    def _start_level(self) -> None:
        """(Re)charge la carte et remet tout à son point de départ (les portes ouvertes se referment)."""
        self.tilemap = Tilemap.from_file(self.map_path)
        starts = self.tilemap.spawns_of("player")
        if not starts:
            raise ValueError(f"La carte {self.map_path} n'a pas de point de départ 'P'")
        ts = self.tilemap.tile_size
        start = starts[0].center(ts)

        self.player = Player(start.x, start.y)
        self.inventory = Inventory()
        self.guards = [Guard.from_spawn(self.tilemap, s) for s in self.tilemap.spawns_of("guard")]
        self.doors = build_doors(self.tilemap)
        self.goal = get_objective(self.mission.objective) if self.mission else infer_objective(self.tilemap)
        self.terminals = [Terminal(*s.center(ts), self.tilemap.terminal_spec((s.tx, s.ty))) for s in self.tilemap.spawns_of("terminal")]
        self.cameras = [SecurityCamera(spec, ts) for spec in self.tilemap.cameras]
        self.lights_out: dict[int, float] = {}  # lampe -> secondes avant qu'elle se rallume (lumière coupée depuis un terminal)
        self.player_light = 1.0  # éclairement (0..1) à la position du joueur
        kind = RELEASE if self.goal is STEAL_SHIP else POWER
        self.consoles = [PowerConsole(*s.center(ts), kind) for s in self.tilemap.spawns_of("console")]
        self.lockers = [Locker(*s.center(ts)) for s in self.tilemap.spawns_of("uniform")]  # casiers d'officier : on y dérobe un uniforme
        self.prisoners = [Prisoner(*s.center(ts)) for s in self.tilemap.spawns_of("prisoner")] if self.goal is FREE_PRISONER else []
        self.tilemap.ship_hold = 0.0 if self.goal is STEAL_SHIP else None  # rayons tracteurs et attaches actifs jusqu'à la libération
        exits = self.tilemap.spawns_of("exit")
        self.exit_pad = (
            ExitPad(
                *exits[0].center(ts),
                ready=lambda inventory: self.exit_ready,
                missing=lambda: self.exit_missing,
                label="Embarquer" if self.goal is STEAL_SHIP else "Extraction",
            )
            if exits
            else None
        )
        self.pickups = [Pickup(*s.center(ts), Item(kind, s.level)) for s in self.tilemap.spawns if (kind := PICKUP_SPAWNS.get(s.kind))]
        self.decoys: list[Decoy] = []
        self.field_buttons = [FieldButton(spec, ts) for spec in self.tilemap.buttons.values()]
        exit_tile = (exits[0].tx, exits[0].ty) if exits else None
        reinforcement_tiles = [(s.tx, s.ty) for s in self.tilemap.spawns_of("reinforcement")]
        self.difficulty = get_difficulty(self.game.prefs.difficulty).for_map(self.tilemap.settings)  # + les réglages de la carte
        for guard in self.guards:
            guard.sensitivity = self.difficulty.detect
        self._field_light_positions = self._field_lights()
        self.lighting = Lighting(self.tilemap)
        self.lighting.enabled = self.game.prefs.lighting
        self.alert = AlertSystem(self.game.events, self.tilemap, reinforcement_tiles, exit_tile, self.difficulty)
        self.interaction.reset()
        if getattr(self, "ambience", None) is not None:
            self.ambience.stop()  # la boucle précédente se tait avant de recharger la carte
        self.tips = TipTracker(self.tilemap.tip_zones, self.tilemap.tile_size)  # astuces de la carte (entraînement)
        self.effects = Effects(self.tilemap, lamps=[(lamp.position(ts), lamp.color) for lamp in self.lighting.lamps])
        self.ambience = Ambience(self.game.audio, self.tilemap, self._ambient_sources())
        self.director.set_acoustics(Acoustics(self.tilemap))
        self.director.set_anchors(
            {button.id: button.pos for button in self.field_buttons},
            {fid: self._field_center(f) for fid, f in self.tilemap.fields.items()},
        )
        self.hud.clear_notifications()
        self._interact_pressed = False
        self._throw_requested = False
        self.mission_time, self.alert_count, self.decoys_thrown = 0.0, 0, 0  # statistiques de la tentative
        self._results_shown = False
        self.caught = False
        self.won = False
        self.failed = False  # verrouillage du croiseur : le chronomètre a atteint zéro
        self.camera = Camera(*SCREEN_SIZE, self.tilemap.pixel_width, self.tilemap.pixel_height)
        self.camera.shake_enabled = self.game.prefs.screen_shake
        self.camera.snap_to(self.player.pos)
        self.camera.follow_pivot(self.player.pos)
        self._last_player_pos = pygame.Vector2(self.player.pos)

    def _field_lights(self) -> list[pygame.Vector2]:
        """Points lumineux régulièrement espacés le long de chaque champ de force."""
        ts = self.tilemap.tile_size
        positions = []
        for prop in self.tilemap.props:
            if prop.kind != "field":
                continue
            length = max(prop.w, prop.h) * ts
            count = max(1, round(length / FIELD_LIGHT_SPACING))
            for i in range(count):
                along = (i + 0.5) * length / count
                positions.append(pygame.Vector2(prop.x * ts + (along if prop.w > prop.h else ts / 2), prop.y * ts + (along if prop.h >= prop.w else ts / 2)))
        return positions

    def _field_center(self, field) -> pygame.Vector2:
        """Centre (px) de la première ligne d'un champ commutable."""
        x, y, w, h = field.runs[0]
        ts = self.tilemap.tile_size
        return pygame.Vector2((x + w / 2) * ts, (y + h / 2) * ts)

    def _ambient_sources(self) -> list[AmbientSource]:
        """Ce qui bourdonne dans la carte : moteurs, lampes (éteintes sans courant), champs actifs, terminaux, consoles."""
        ts = self.tilemap.tile_size
        sources = [AmbientSource("engine", pygame.Vector2((p.x + p.w / 2) * ts, (p.y + p.h / 2) * ts)) for p in self.tilemap.props if p.kind == "ship"]
        sources += [AmbientSource("lamp", lamp.position(ts), lambda i=i: self.power_on and i not in self.lights_out) for i, lamp in enumerate(self.lighting.lamps)]
        sources += [AmbientSource("field", pos) for pos in self._field_light_positions]
        sources += [AmbientSource("field", self._field_center(f), lambda f=f: f.active) for f in self.tilemap.fields.values()]
        sources += [AmbientSource("terminal", t.pos, lambda t=t: not t.hacked) for t in self.terminals]
        sources += [AmbientSource("console", c.pos, lambda c=c: not c.cut) for c in self.consoles]
        return sources

    def restart(self) -> None:
        """Recommence la mission (carte rechargée, difficulté relue dans les préférences)."""
        self._start_level()

    # --- Cycle de vie --------------------------------------------------------
    def on_enter(self) -> None:
        for name, handler in self._handlers.items():
            self.game.events.subscribe(name, handler)
        for name, handler in self._shake_handlers.items():
            self.game.events.subscribe(name, handler)
        for name, handler in self._tip_handlers.items():
            self.game.events.subscribe(name, handler)
        self.director.attach()
        self.game.audio.start_music()

    def on_exit(self) -> None:
        for name, handler in self._handlers.items():
            self.game.events.unsubscribe(name, handler)
        for name, handler in self._shake_handlers.items():
            self.game.events.unsubscribe(name, handler)
        for name, handler in self._tip_handlers.items():
            self.game.events.unsubscribe(name, handler)
        self.director.detach()
        self.ambience.stop()
        self.game.audio.set_tension(0.0)

    def on_resume(self) -> None:
        """Retour de la pause : les réglages ont pu changer (éclairage)."""
        self.lighting.enabled = self.game.prefs.lighting
        self.camera.shake_enabled = self.game.prefs.screen_shake
        if not self.camera.shake_enabled:
            self.camera.trauma = 0.0

    def pause(self) -> None:
        self.game.scenes.push(PauseScene(self.game, self))

    # --- Réactions aux événements -------------------------------------------
    def _on_noise(self, pos: pygame.Vector2, radius: float) -> None:
        """Un bruit est émis : les gardes à portée vont enquêter."""
        for guard in self.guards:
            guard.hear(self.tilemap, pos, radius)

    def _on_item_picked(self, item: Item) -> None:
        self.hud.notify(f"Ramassé : {item.label}", item_color(item))

    def _on_denied(self, message: str) -> None:
        self.hud.flash_denied()  # le motif est déjà dans l'invite affichée

    def _on_terminal_hacked(self, terminal: Terminal) -> None:
        self.hud.notify(STEAL_PLANS.done, COLORS["status_calm"])
        self.effects.burst("terminal", terminal.pos)

    def _on_terminal_opened(self, terminal: Terminal) -> None:
        """Le joueur utilise un terminal : le jeu s'arrête et un menu propose ce que ce terminal sait faire."""
        from game.scenes.terminal_scene import TerminalScene  # import tardif : cette scène a besoin de `PlayScene`

        self.game.scenes.push(TerminalScene(self.game, self, terminal))

    def _on_camera_spotted(self, pos: pygame.Vector2, camera) -> None:
        """Une caméra a repéré le joueur : elle prévient les gardes les plus proches, qui viennent voir sur place."""
        self.hud.notify("Une caméra vous a repéré !", COLORS["status_suspect"])
        listeners = [g for g in self.guards if g.state is not GuardState.CHASE]
        listeners.sort(key=lambda g: g.pos.distance_squared_to(pos))
        for guard in listeners[:CAMERA_RESPONDERS]:
            guard.alarm(self.tilemap, pos)

    def _on_ships_released(self, console: PowerConsole) -> None:
        self.hud.notify(STEAL_SHIP.done, COLORS["status_calm"])
        self.effects.burst("console", console.pos)

    def _on_prisoner_freed(self, prisoner: Prisoner) -> None:
        self.hud.notify(FREE_PRISONER.done, COLORS["status_calm"])
        self.effects.burst("terminal", prisoner.pos)

    def _on_power_cut(self, console: PowerConsole) -> None:
        self.hud.notify(CUT_POWER.done, COLORS["status_calm"])
        self.effects.burst("console", console.pos)

    def _on_field_toggled(self, field: str, active: bool) -> None:
        """Un champ bascule : une gerbe d'étincelles à chaque ligne."""
        ts = self.tilemap.tile_size
        for x, y, w, h in self.tilemap.fields[field].runs:
            self.effects.burst("field", pygame.Vector2((x + w / 2) * ts, (y + h / 2) * ts))

    def _on_mission_complete(self) -> None:
        self.won = True

    def _on_decoy_thrown(self, pos: pygame.Vector2) -> None:
        self.decoys_thrown += 1

    def _on_alert_raised(self, pos: pygame.Vector2) -> None:
        self.alert_count += 1
        self.hud.notify("ALERTE GÉNÉRALE : fuyez avant le verrouillage !", COLORS["status_alert"])
        if self.inventory.uniform_worn:  # l'alerte est donnée : plus personne ne se laisse tromper
            self.hud.notify("Couverture grillée : l'uniforme ne trompe plus personne", COLORS["status_suspect"])

    def _on_uniform_stolen(self, locker: Locker) -> None:
        self.hud.notify(f"Uniforme dérobé : {bindings.label('disguise')} pour l'enfiler", COLORS["status_calm"])
        self.effects.burst("terminal", locker.pos)

    def _toggle_disguise(self) -> None:
        """Enfile ou retire l'uniforme dérobé. Sans uniforme, ou une fois l'alerte donnée, cela ne trompe personne."""
        if not self.inventory.has_uniform:
            self.hud.notify("Vous n'avez pas d'uniforme", COLORS["text_dim"])
            return
        worn = self.inventory.toggle_uniform()
        self.game.events.emit("disguise_changed", worn=worn)
        if worn and self.alert.active:
            self.hud.notify("Inutile : l'alerte est donnée, tout le monde vous cherche", COLORS["status_suspect"])
        elif worn:
            self.hud.notify("Uniforme enfilé : marchez, sans courir, et gardez vos distances", COLORS["status_calm"])
        else:
            self.hud.notify("Uniforme retiré", COLORS["text_dim"])

    @property
    def disguise_state(self) -> str | None:
        """Pour le HUD : 'worn' (on vous prend pour un officier), 'blown' (porté, mais l'alerte est donnée), 'stowed' (dans le sac), None."""
        if not self.inventory.has_uniform:
            return None
        if self.inventory.uniform_worn:
            return "blown" if self.alert.active else "worn"
        return "stowed"

    def _on_reinforcements(self, count: int) -> None:
        self.hud.notify("Des renforts arrivent", COLORS["status_suspect"])

    def _on_lockdown(self) -> None:
        self.failed = True

    # --- État ----------------------------------------------------------------
    @property
    def threat(self) -> GuardState:
        """État le plus alarmant parmi les gardes (une caméra qui commence à repérer le joueur le rend au moins suspect)."""
        worst = max((g.state for g in self.guards), key=lambda state: state.threat, default=GuardState.PATROL)
        if worst.threat < GuardState.INVESTIGATE.threat and any(c.awareness > 0.25 for c in self.cameras):
            return GuardState.INVESTIGATE
        return worst

    @property
    def stats(self) -> MissionStats:
        """Temps de jeu (hors pause), alertes générales et leurres de la tentative en cours."""
        return MissionStats(self.mission_time, self.alert_count, self.decoys_thrown)

    @property
    def over(self) -> bool:
        return self.caught or self.won or self.failed

    @property
    def objective_done(self) -> bool:
        """L'objectif de la mission est accompli : la sortie s'ouvre."""
        if self.goal is STEAL_PLANS:
            return self.inventory.count_kind(ItemKind.DATA) > 0
        if self.goal is STEAL_UNIFORM:
            return self.inventory.has_uniform
        if self.goal in (CUT_POWER, STEAL_SHIP):
            return bool(self.consoles) and all(c.cut for c in self.consoles)
        if self.goal is FREE_PRISONER:
            return bool(self.prisoners) and all(p.freed for p in self.prisoners)
        return False

    @property
    def exit_ready(self) -> bool:
        """On peut partir : l'objectif est accompli et, pour une évasion, le prisonnier a suivi jusqu'à la sortie."""
        if not self.objective_done:
            return False
        if self.goal is FREE_PRISONER and self.exit_pad is not None:
            return all(p.pos.distance_to(self.exit_pad.pos) <= PRISONER_EXIT_RANGE for p in self.prisoners)
        return True

    @property
    def exit_missing(self) -> str:
        """Ce que dit la zone d'extraction tant qu'on ne peut pas partir."""
        if self.goal is FREE_PRISONER and self.objective_done:
            return "Attendez le prisonnier"
        return self.goal.missing

    @property
    def power_on(self) -> bool:
        return not any(c.cut for c in self.consoles if c.kind == POWER)

    @property
    def objective(self) -> str:
        """Consigne affichée dans le HUD."""
        if self.won:
            return ""
        if self.objective_done:
            return self.goal.flee if self.alert.active else self.goal.calm
        return self.goal.goal

    @property
    def interactables(self) -> list:
        return [*self.doors, *self.field_buttons, *self.terminals, *self.consoles, *self.prisoners, *self.lockers, *([self.exit_pad] if self.exit_pad else [])]

    # --- Boucle --------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.WINDOWFOCUSLOST:  # on ne laisse pas les gardes jouer pendant que le joueur est parti
            self.pause()
            return
        if event.type != pygame.KEYDOWN:
            return
        if event.key == QUIT_KEY:
            self.pause()
        elif event.key == DEBUG_KEY:
            self.debug = not self.debug
        elif self.game.dev is not None and event.key in DEV_KEYS.values():
            self._dev_key(event.key)
        elif event.key == LIGHTING_KEY:
            self.lighting.toggle()
            self.game.prefs.lighting = self.lighting.enabled
            self.game.prefs.save()
        elif event.key == RESTART_KEY and self.over:
            self.restart()
        elif event.key in bindings.current.keys("interact"):
            self._interact_pressed = True
        elif event.key in bindings.current.keys("throw"):
            self._throw_requested = True
        elif event.key in bindings.current.keys("disguise"):
            self._toggle_disguise()

    def update(self, dt: float) -> None:
        self.time += dt
        self.hud.update(dt)
        self.lights_out = {i: left - dt for i, left in self.lights_out.items() if left - dt > 0}
        self.lighting.update(dt, self.alert.active, self.power_on, self.lights_out)
        pressed, throw = self._interact_pressed, self._throw_requested
        self._interact_pressed = self._throw_requested = False

        if not self.over:
            self.mission_time += dt
            inp = read_input()
            aim_world = self.camera.screen_to_world(inp.aim_screen)
            self._aim_offset = pygame.Vector2(inp.aim_screen) - pygame.Vector2(self.camera.view_size) / 2 if inp.aim_active else None
            self.player.update(dt, self.tilemap, inp, aim_world)
            self.player.ghost = self.game.dev is not None and self.game.dev.ghost
            self.player.disguised = self.inventory.uniform_worn and not self.alert.active  # une alerte générale grille la couverture
            if self.player.made_step:
                self.effects.footstep(self.player.pos, self.player.stance.value)
                if self.player.heard_radius > 0:  # un officier qui marche fait un bruit que personne ne relève
                    self.game.events.emit("noise", pos=pygame.Vector2(self.player.pos), radius=self.player.heard_radius)
                self.game.events.emit("footstep", stance=self.player.stance.value)
            if throw:
                self._throw_decoy(aim_world)
            self._update_objects(dt)
            self._update_visibility()
            self._update_terminals(dt)

            collect_pickups(self.player.pos, self.inventory, self.pickups, self.game.events)
            self.interaction.update(dt, self.player.pos, self.tilemap, self.inventory, self.interactables, pressed=pressed, held=inp.interact)
            for guard in self.guards:
                guard.update(dt, self.tilemap, self.player)
            for camera in self.cameras:
                if camera.update(dt, self.tilemap, self.player):
                    self.game.events.emit("camera_spotted", pos=pygame.Vector2(self.player.pos), camera=camera)
            # Un champ qui doit s'activer attend que personne ne soit dans sa zone : on ne coince ni joueur ni garde.
            self.tilemap.update_fields(self._occupant_boxes())
            self.guards.extend(self.alert.update(dt, self.guards, self.player))
            self._retire_reinforcements()
            invincible = self.game.dev is not None and self.game.dev.invincible
            if not self.over and not invincible and any(guard.can_catch(self.player) for guard in self.guards):
                self.caught = True
                self.game.events.emit("player_caught")
        self.director.update(
            dt,
            self.guards,
            self.player.pos,
            hacking=not self.over and self.hack_progress > 0,
            alert_active=self.alert.active and not self.over,
        )
        self._update_effects(dt)
        self.ambience.update(dt, self.player.pos)
        self._update_camera(dt)
        self.tips.update(
            dt,
            self.player.pos,
            self.player.stance is Stance.CROUCH,
            self.inventory.count_kind(ItemKind.DECOY) > 0,
            hidden=self.over,
        )
        if self.won and self.mission is not None and not self._results_shown:
            self._results_shown = True
            self._show_results()

    # --- Terminaux, lumière, caméras ----------------------------------------------------
    @property
    def hack_progress(self) -> float:
        """Avancement (0..1) de ce que le joueur est en train de faire : connexion à un terminal, ou action maintenue."""
        jobs = [t.job.progress for t in self.terminals if t.job is not None]
        return max([self.interaction.progress, *jobs])

    def terminal_actions(self, terminal: Terminal) -> list[tuple[str, str, bool, str]]:
        """Ce que le menu d'un terminal propose : (action, libellé, disponible, précision), dans l'ordre des pouvoirs."""
        actions = []
        for capability in terminal.capabilities:
            label = terminal_actions.LABELS[capability]
            if capability == terminal_actions.DATA:
                done = terminal.hacked
                actions.append((capability, label, not done, "Données déjà téléchargées" if done else f"Rester près du terminal ({self._seconds(capability)})"))
            elif capability == terminal_actions.CELLS:
                closed = [d for d in self.doors if d.cell and not d.is_open]
                if not any(d.cell for d in self.doors):
                    actions.append((capability, label, False, "Aucune cellule à ouvrir"))
                elif not closed:
                    actions.append((capability, label, False, "Cellules déjà ouvertes"))
                else:
                    actions.append((capability, label, True, f"{len(closed)} cellule(s), le bruit attire les gardes"))
            elif capability == terminal_actions.CAMERAS:
                targets = [c for c in self.cameras if terminal.spec.controls(c.group)]
                if not targets:
                    actions.append((capability, label, False, "Aucune caméra à commander"))
                elif all(not c.active for c in targets):
                    actions.append((capability, label, False, "Déjà désactivées"))
                else:
                    actions.append((capability, label, True, f"{len(targets)} caméra(s), pendant {CAMERA_OFF_TIME:.0f} s"))
            else:
                lamps = self._room_lamps(terminal)
                if not lamps:
                    actions.append((capability, label, False, "Aucune lampe dans cette salle"))
                elif all(i in self.lights_out for i in lamps):
                    actions.append((capability, label, False, "La salle est déjà dans le noir"))
                else:
                    actions.append((capability, label, True, f"Pendant {LIGHTS_OUT_TIME:.0f} s : on s'y voit moins"))
        return actions

    @staticmethod
    def _seconds(capability: str) -> str:
        from game.settings import TERMINAL_JOB_TIME

        return f"{TERMINAL_JOB_TIME[capability]:.1f} s"

    def _room_lamps(self, terminal: Terminal) -> list[int]:
        """Indices des lampes de la salle du terminal (la zone qu'il occupe, portes fermées comprises)."""
        region = self.tilemap.region_of(*terminal.tile)
        return [i for i, lamp in enumerate(self.lighting.lamps) if self.tilemap.region_of(*lamp.tile) == region]

    def start_terminal_job(self, terminal: Terminal, action: str) -> None:
        """Le joueur a choisi une opération : la connexion démarre, il doit rester près du terminal jusqu'à son terme."""
        terminal.start(action)

    def _update_terminals(self, dt: float) -> None:
        for terminal in self.terminals:
            outcome = terminal.advance(dt, self.player.pos)
            if outcome == "lost":
                self.hud.notify("Connexion perdue : restez près du terminal", COLORS["status_suspect"])
            elif outcome == terminal_actions.DATA:
                terminal.hacked = True
                self.inventory.add(Item(ItemKind.DATA))
                self.game.events.emit("terminal_hacked", terminal=terminal)
            elif outcome == terminal_actions.CAMERAS:
                targets = [c for c in self.cameras if terminal.spec.controls(c.group)]
                for camera in targets:
                    camera.disable(CAMERA_OFF_TIME)
                self.hud.notify(f"Caméras désactivées pendant {CAMERA_OFF_TIME:.0f} s", COLORS["status_calm"])
                self.game.events.emit("cameras_disabled", terminal=terminal, count=len(targets))
            elif outcome == terminal_actions.CELLS:
                opened = [d for d in self.doors if d.cell and not d.is_open]
                for door in opened:
                    self.tilemap.open_door(door.tiles)
                    door.is_open = True
                self.hud.notify("Cellules ouvertes", COLORS["status_calm"])
                self.game.events.emit("cells_opened", terminal=terminal, count=len(opened))
                self.game.events.emit("noise", pos=pygame.Vector2(terminal.pos), radius=CELLS_OPEN_NOISE)
            elif outcome == terminal_actions.LIGHTS:
                for i in self._room_lamps(terminal):
                    self.lights_out[i] = LIGHTS_OUT_TIME
                self.hud.notify(f"Lumière coupée dans la salle pendant {LIGHTS_OUT_TIME:.0f} s", COLORS["status_calm"])
                self.game.events.emit("lights_out", terminal=terminal)
                self.game.events.emit("noise", pos=pygame.Vector2(terminal.pos), radius=LIGHTS_OUT_NOISE)  # les disjoncteurs claquent

    def _update_visibility(self) -> None:
        """Éclairement à la position du joueur : il règle sa visibilité pour les gardes et les caméras (B5)."""
        sources = self.lighting.light_sources(self.tilemap)
        sources += [(pos, radius, color, intensity) for pos, radius, color, intensity in self.tilemap.decor_lights(None, self.time, around=self.player.pos)]
        self.player_light = light_at(self.tilemap, self.player.pos, self.lighting.base_light(), sources)
        self.player.light_factor = visibility_factor(self.player_light)

    def _update_camera(self, dt: float) -> None:
        """La caméra suit le joueur en prenant de l'avance, se penche vers le curseur et zoome selon la situation."""
        velocity = (self.player.pos - self._last_player_pos) / dt if dt > 0 else None
        self._last_player_pos.update(self.player.pos)
        self.camera.zoom_target = self._zoom_target()
        self.camera.update(self.player.pos, dt, velocity, None if self.over else self._aim_offset)
        self.camera.follow_pivot(self.player.pos)  # le zoom se fait autour du joueur, pas du centre de l'écran

    def _zoom_target(self) -> float:
        """Le zoom voulu : serré à la capture, sur l'action quand on pirate, un peu en poursuite ou accroupi."""
        if self.caught:
            return CAMERA_ZOOM["caught"]
        if self.over:
            return 1.0
        if self.hack_progress > 0:
            return CAMERA_ZOOM["focus"]
        if self.threat is GuardState.CHASE or self.alert.active:
            return CAMERA_ZOOM["chase"]
        if self.player.stance is Stance.CROUCH:
            return CAMERA_ZOOM["crouch"]
        return 1.0

    def _shake(self, amount: float, pos=None) -> None:
        """Une secousse ; `pos` (monde) la localise : plus on est loin, moins on la sent."""
        if pos is not None:
            amount *= attenuation(self.player.pos.distance_to(pos), SHAKE_RANGE)
        self.camera.add_trauma(amount)

    def _update_effects(self, dt: float) -> None:
        target = self.interaction.target
        if not self.over:
            for terminal in self.terminals:
                if terminal.job is not None:
                    self.effects.hacking("terminal", terminal.pos, terminal.job.progress, dt)
            if self.interaction.progress > 0 and isinstance(target, PowerConsole):
                self.effects.hacking("console", target.pos, self.interaction.progress, dt)
        for pos in self.effects.update(dt, self.player.pos, self.guards, self.camera.visible_rect, self.power_on, self.lights_out):
            self.game.events.emit("vent_burst", pos=pos)  # un jet de vapeur s'ouvre : le son s'entend d'où il est

    def _door_unlocked(self, door: Door) -> bool:
        """Le voyant de la porte passe à sa couleur quand on peut l'ouvrir : le bon badge, l'uniforme *porté*, ou (cellule) un badge qui la déverrouille."""
        if door.staff:
            return self.inventory.uniform_worn
        return self.inventory.has_keycard(door.level) and not (door.cell and door.level == 0)

    # --- Mode développeur (`--dev`) ---------------------------------------------------
    def _dev_key(self, key: int) -> None:
        """Outils de test : invincibilité, fantôme, équipement, objectif accompli, téléportations."""
        action = next(name for name, value in DEV_KEYS.items() if value == key)
        dev = self.game.dev
        if action in ("invincible", "ghost"):
            state = dev.toggle(action)
            self.hud.notify(f"DEV : {action} {'activé' if state else 'désactivé'}", COLORS["status_suspect"])
        elif action == "loadout":
            self._dev_loadout()
        elif action == "objective":
            self._dev_complete_objective()
        else:
            target = self.goal_spawn() if action == "goto_goal" else next(iter(self.tilemap.spawns_of("exit")), None)
            if target is not None:
                self.player.pos = pygame.Vector2(target.center(self.tilemap.tile_size))
                self.hud.notify("DEV : téléporté", COLORS["status_suspect"])

    def goal_spawn(self):
        """Le point qui porte l'objectif de la mission (terminal de données, console, prisonnier, casier), ou None."""
        return next(iter(objective_spawns(self.tilemap, self.goal)), None)

    def _dev_loadout(self) -> None:
        for level in range(1, MAX_BADGE_LEVEL + 1):
            self.inventory.add(Item(ItemKind.KEYCARD, level))
        self.inventory.add(Item(ItemKind.DECOY), 3)
        self.hud.notify("DEV : badges et leurres ajoutés", COLORS["status_suspect"])

    def _dev_complete_objective(self) -> None:
        if self.goal is STEAL_PLANS:
            if self.inventory.count_kind(ItemKind.DATA) == 0:
                self.inventory.add(Item(ItemKind.DATA))
        elif self.goal is STEAL_UNIFORM:
            if not self.inventory.has_uniform:
                self.inventory.add(Item(ItemKind.UNIFORM))
        elif self.goal is FREE_PRISONER:
            for prisoner in self.prisoners:
                prisoner.freed = True
        else:
            for console in self.consoles:
                console.cut = True
        self.hud.notify("DEV : objectif accompli", COLORS["status_suspect"])

    def _show_results(self) -> None:
        """Mission de campagne réussie : on calcule le score et le rang, on enregistre, puis on affiche les résultats."""
        result = compute_result(self.stats, self.mission.par_time)
        update = self.game.progress.record(self.mission.id, result)
        self.game.progress.save()
        self.game.scenes.push(ResultsScene(self.game, self, self.mission, result, update))

    def _occupant_boxes(self) -> list[tuple[float, float, float, float]]:
        """Boîtes (x, y, largeur, hauteur) du joueur et des gardes : ce qu'un champ qui s'active ne doit pas écraser."""
        return [(*e.top_left, e.width, e.height) for e in (self.player, *self.guards)]

    def _retire_reinforcements(self) -> None:
        """Les renforts dont le temps est écoulé quittent la partie."""
        staying = [g for g in self.guards if not g.expired]
        if len(staying) != len(self.guards):
            self.guards[:] = staying
            self.hud.notify("Les renforts se retirent", COLORS["status_calm"])

    def _update_ship_hold(self, dt: float) -> None:
        """Les rayons tracteurs s'éteignent et les attaches s'ouvrent en `SHIP_RELEASE_FADE` secondes une fois la console actionnée."""
        if self.tilemap.ship_hold is None:
            return
        released = bool(self.consoles) and all(c.cut for c in self.consoles)
        target = 1.0 if released else 0.0
        step = dt / SHIP_RELEASE_FADE
        self.tilemap.ship_hold = min(target, self.tilemap.ship_hold + step) if target > self.tilemap.ship_hold else max(target, self.tilemap.ship_hold - step)

    def _update_objects(self, dt: float) -> None:
        for obj in (*self.pickups, *self.terminals, *self.consoles, *self.doors, *self.field_buttons):
            obj.update(dt)
        for locker in self.lockers:
            locker.update(dt)
        for prisoner in self.prisoners:
            prisoner.update(dt, self.tilemap, self.player.pos)
        self._update_ship_hold(dt)
        if self.exit_pad:
            self.exit_pad.update(dt)
        for decoy in self.decoys:
            decoy.update(dt)
            if decoy.made_beep:
                self.game.events.emit("noise", pos=pygame.Vector2(decoy.pos), radius=DECOY_NOISE)
                self.game.events.emit("decoy_beep", pos=pygame.Vector2(decoy.pos))
        self.decoys = [d for d in self.decoys if not d.expired]

    def _throw_decoy(self, aim_world: pygame.Vector2) -> None:
        """Lance un leurre vers la souris, à portée limitée et arrêté par les murs."""
        if not self.inventory.remove(Item(ItemKind.DECOY)):
            self.hud.notify("Aucun leurre", COLORS["text_dim"])
            return
        offset = aim_world - self.player.pos
        direction = offset.normalize() if offset.length_squared() > 0 else pygame.Vector2(self.player.facing)
        distance = min(offset.length(), THROW_RANGE)
        wall = cast_ray(self.tilemap, self.player.pos, direction, distance, solid=True)  # un leurre ne traverse pas un champ de force
        if wall < distance:  # le leurre retombe devant le mur
            distance = max(0.0, wall - DECOY_SIZE)
        self.decoys.append(Decoy(*(self.player.pos + direction * distance)))
        self.game.events.emit("decoy_thrown", pos=pygame.Vector2(self.decoys[-1].pos))

    # --- Dessin --------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        """Le monde, éventuellement zoomé (mise à l'échelle de l'image), puis l'interface par-dessus, à l'échelle normale."""
        if self.camera.zoom > 1.0 + CAMERA_ZOOM_EPS:
            size = surface.get_size()
            if self._world_buffer is None or self._world_buffer.get_size() != size:
                self._world_buffer = pygame.Surface(size, 0, surface)
            self._draw_world(self._world_buffer)
            pygame.transform.smoothscale(self._world_buffer.subsurface(self.camera.crop_rect()), size, surface)
        else:
            self._draw_world(surface)
        self._draw_interface(surface)

    def _draw_world(self, surface: pygame.Surface) -> None:
        surface.fill(COLORS["background"])
        if self.tilemap.has_void:
            self.space.draw(surface, self.camera, self.time)
        self.tilemap.draw(surface, self.camera, self.time)
        self.tilemap.draw_decor(surface, self.camera, self.time)
        view = self.camera.visible_rect.inflate(self.tilemap.tile_size * 2, self.tilemap.tile_size * 2)
        self._draw_objects(surface, view)
        self.effects.draw_soft(surface, self.camera)
        self.lighting.draw(surface, self.camera, self.tilemap, self._light_specs())
        self.effects.draw_glow(surface, self.camera)
        self.overlay.draw_under(surface, self.camera, self.tilemap, self.guards, self.cameras)
        for guard in self.guards:
            if view.collidepoint(guard.pos):
                guard.draw(surface, self.camera)
        self.player.draw(surface, self.camera)
        self.overlay.draw_over(surface, self.camera, self.guards, debug=self.debug)
        if self.debug:
            self._draw_debug(surface)

    def _draw_interface(self, surface: pygame.Surface) -> None:
        shown = self.tips.current
        if shown is not None:
            self.hud.draw_tip(surface, format_tip(shown[0].text), shown[1])
        if not self.over and self.interaction.prompt is not None:
            target = self.interaction.target
            anchor = self.camera.zoom_point(self.camera.world_to_screen(target.anchor))  # l'invite suit l'objet zoomé
            self.hud.draw_prompt(surface, (round(anchor[0]), round(anchor[1])), self.interaction.prompt, self.interaction.progress)
        tile = self.tilemap.world_to_tile(*self.player.pos)
        self.hud.draw(
            surface,
            fps=self.game.clock.get_fps(),
            player=self.player,
            tile=tile,
            debug=self.debug,
            threat=self.threat,
            inventory=self.inventory,
            objective=self.objective,
            visibility=visibility_zone(self.player_light, self.lighting.base_light()),
            disguise=self.disguise_state,
            lockdown_left=self.alert.time_left if self.alert.active else None,
        )
        if self.game.dev is not None:
            self.hud.draw_dev(surface, self.game.dev.active())
        if self.failed:
            self.hud.draw_locked_down(surface)
        elif self.caught:
            self.hud.draw_caught(surface)
        elif self.won and self.mission is None:  # une mission de campagne a son propre écran de résultats
            self.hud.draw_won(surface)

    def _light_specs(self) -> list[LightSpec]:
        """Lumières mobiles de l'image courante : tout ce qui brille ou éclaire autour de soi."""
        specs = [LightSpec(pygame.Vector2(self.player.pos), shadowed=True, **PLAYER_LIGHT)]
        radius, intensity = SPOT_LIGHTS["field"]
        for pos, radius_px, color, glow in self.tilemap.decor_lights(self.camera, self.time):
            specs.append(LightSpec(pygame.Vector2(pos), radius_px, color, glow))  # les lanternes éclairent un peu
        for pos in self._field_light_positions:  # les champs de force éclairent leurs abords
            specs.append(LightSpec(pos, radius, COLORS["field_glow"], intensity))
        for guard in self.guards:
            heat = 1.0 if guard.state is GuardState.CHASE else guard.awareness
            specs.append(LightSpec(pygame.Vector2(guard.pos), **GUARD_AURA))
            specs.append(
                LightSpec(
                    pygame.Vector2(guard.pos),
                    GUARD_VISION_RANGE,
                    lerp_color(GUARD_TORCH["color"], GUARD_TORCH["alert_color"], heat),
                    GUARD_TORCH["intensity"],
                    facing=guard.angle,
                    fov=GUARD_FOV,
                )
            )

        def spot(kind: str, pos, color, factor: float = 1.0) -> None:
            radius, intensity = SPOT_LIGHTS[kind]
            specs.append(LightSpec(pygame.Vector2(pos), radius, color, intensity * factor))

        for terminal in self.terminals:
            spot("terminal", terminal.pos, COLORS["terminal_done" if terminal.hacked else "terminal_screen"])
        for console in self.consoles:
            spot("console", console.pos, COLORS["console_dead" if console.cut else "console_live"], 0.4 if console.cut else 1.0)
        if self.exit_pad:
            ready = self.exit_pad.is_ready(self.inventory)
            spot("exit", self.exit_pad.pos, COLORS["exit_ready" if ready else "exit_idle"], 1.0 if ready else 0.35)
        for f in self.tilemap.fields.values():  # champs commutables : lueur au centre de chaque ligne, qui clignote en attente
            if not (f.active or f.pending):
                continue
            blink = 1.0 if f.active else 0.4 + 0.6 * (int(self.time * FIELD_PENDING_BLINK * 2) % 2 == 0)
            for x, y, w, h in f.runs:
                center = ((x + w / 2) * self.tilemap.tile_size, (y + h / 2) * self.tilemap.tile_size)
                spot("gate", center, COLORS[f"link_{f.color}"], blink)
        for button in self.field_buttons:
            spot("button", button.pos, button.color, 0.4 if button.cooldown > 0 else 1.0)
        for door in self.doors:
            if door.progress < 1.0:  # la lueur de la porte s'éteint pendant qu'elle s'ouvre
                spot("door", door.anchor, COLORS[f"badge_{door.level}"], 1.0 - door.progress)
        for pickup in self.pickups:
            spot("pickup", pickup.pos, item_color(pickup.item))
        for decoy in self.decoys:
            spot("decoy", decoy.pos, COLORS["item_decoy"], 1.0 if decoy.made_beep else 0.35)
        return specs

    def _draw_objects(self, surface: pygame.Surface, view: pygame.Rect) -> None:
        for door in self.doors:
            if view.colliderect(door.rect):
                door.draw(surface, self.camera, unlocked=self._door_unlocked(door))
        if self.exit_pad and view.collidepoint(self.exit_pad.pos):
            self.exit_pad.draw(surface, self.camera, ready=self.exit_pad.is_ready(self.inventory))
        for terminal in self.terminals:
            if view.collidepoint(terminal.pos):
                terminal.draw(surface, self.camera)
        for locker in self.lockers:
            if view.collidepoint(locker.pos):
                searching = self.interaction.target is locker
                locker.draw(surface, self.camera, self.interaction.progress if searching else 0.0)
        for prisoner in self.prisoners:
            if view.collidepoint(prisoner.pos):
                prisoner.draw(surface, self.camera)
        for security_camera in self.cameras:
            if view.collidepoint(security_camera.pos):
                security_camera.draw(surface, self.camera, self.time)
        for console in self.consoles:
            if view.collidepoint(console.pos):
                cutting = self.interaction.target is console
                console.draw(surface, self.camera, self.interaction.progress if cutting else 0.0)
        for button in self.field_buttons:
            if view.collidepoint(button.pos):
                button.draw(surface, self.camera)
        for obj in (*self.pickups, *self.decoys):
            if view.collidepoint(obj.pos):
                obj.draw(surface, self.camera)

    def _draw_debug(self, surface: pygame.Surface) -> None:
        ts = self.tilemap.tile_size
        px, py = self.tilemap.world_to_tile(*self.player.pos)
        for ty in range(py - 2, py + 3):  # tuiles solides autour du joueur
            for tx in range(px - 2, px + 3):
                if self.tilemap.is_solid(tx, ty):
                    corner = self.camera.world_to_screen((tx * ts, ty * ts))
                    pygame.draw.rect(surface, COLORS["debug_solid"], (*corner, ts, ts), 1)

        hitbox = self.player.rect
        hitbox.topleft = self.camera.world_to_screen(hitbox.topleft)
        pygame.draw.rect(surface, COLORS["debug_hitbox"], hitbox, 1)

        radius = self.player.noise_radius
        if radius > 0:
            center = self.camera.world_to_screen(self.player.pos)
            pygame.draw.circle(surface, COLORS["debug_noise"], center, radius, 1)

        self._draw_field_links(surface)
        for guard in self.guards:  # chemin A* en cours de chaque garde
            if guard.follower.finished:
                continue
            points = [self.camera.world_to_screen(p) for p in (guard.pos, *guard.follower.waypoints)]
            pygame.draw.lines(surface, COLORS["debug_path"], False, points, 2)
            for point in points[1:]:
                pygame.draw.circle(surface, COLORS["debug_path"], point, 3)

    def _draw_field_links(self, surface: pygame.Surface) -> None:
        """Debug : un trait entre chaque bouton et ses champs liés, avec l'état de chacun (fermé = actif, ouvert, attente)."""
        ts = self.tilemap.tile_size
        for button in self.field_buttons:
            start = self.camera.world_to_screen(button.pos)
            label = self.hud.small.render(f"bouton {button.id}", True, button.color)
            surface.blit(label, label.get_rect(midbottom=(start[0], start[1] - 10)))
            for field_id in button.spec.fields:
                f = self.tilemap.fields[field_id]
                x, y, w, h = f.runs[0]
                end = self.camera.world_to_screen(((x + w / 2) * ts, (y + h / 2) * ts))
                pygame.draw.line(surface, button.color, start, end, 1)
                state = "attente" if f.pending else "fermé" if f.active else "ouvert"
                text = self.hud.small.render(f"{field_id} : {state}", True, COLORS[f"link_{f.color}"])
                surface.blit(text, text.get_rect(midtop=(end[0], end[1] + 12)))
        for f in self.tilemap.fields.values():
            if not f.buttons:  # champ orphelin : on le signale aussi
                x, y, w, h = f.runs[0]
                pos = self.camera.world_to_screen(((x + w / 2) * ts, (y + h / 2) * ts))
                text = self.hud.small.render(f"{f.id} : sans bouton", True, COLORS["text_dim"])
                surface.blit(text, text.get_rect(midtop=(pos[0], pos[1] + 12)))
