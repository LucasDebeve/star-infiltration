"""Constantes globales : chemins, affichage, touches, couleurs, réglages du joueur."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pygame

VERSION = "1.0.0"


# --- Chemins -----------------------------------------------------------------
def resource_root(frozen_dir: str | None = None, source_dir: Path | None = None) -> Path:
    """Dossier qui contient `assets/` : celui des sources, ou — dans un exécutable PyInstaller — le dossier où il dépose ses données
    (`sys._MEIPASS`). Les paramètres servent aux tests."""
    frozen = frozen_dir if frozen_dir is not None else getattr(sys, "_MEIPASS", None)
    return Path(frozen) if frozen else (source_dir or Path(__file__).resolve().parent.parent)


ROOT_DIR = resource_root()
ASSETS_DIR = ROOT_DIR / "assets"
MAPS_DIR = ASSETS_DIR / "maps"
CAMPAIGN_FILE = ASSETS_DIR / "campaign.json"
SOUNDS_DIR = ASSETS_DIR / "sounds"

# --- Affichage ---------------------------------------------------------------
TITLE = "Star Infiltration"
SCREEN_SIZE = (1280, 720)  # résolution logique (la fenêtre peut être redimensionnée)
FPS = 60
MAX_DT = 1 / 30  # un gros lag ne doit pas téléporter le joueur à travers un mur

TILE_SIZE = 32

# --- Touches (ZQSD + flèches, pour clavier AZERTY) ---------------------------
# Pour un clavier QWERTY, remplacer K_z/K_q par K_w/K_a.
KEYS = {
    "up": (pygame.K_z, pygame.K_UP),
    "down": (pygame.K_s, pygame.K_DOWN),
    "left": (pygame.K_q, pygame.K_LEFT),
    "right": (pygame.K_d, pygame.K_RIGHT),
    "run": (pygame.K_LSHIFT, pygame.K_RSHIFT),
    "crouch": (pygame.K_LCTRL, pygame.K_c),
    "interact": (pygame.K_e,),  # maintenu : piratage ; appuyé : ouvrir, extraire
    "disguise": (pygame.K_u,),  # enfile ou retire l'uniforme dérobé
}
THROW_KEY = pygame.K_f  # lance un leurre vers la souris
DEBUG_KEY = pygame.K_F3
QUIT_KEY = pygame.K_ESCAPE
RESTART_KEY = pygame.K_r
LIGHTING_KEY = pygame.K_F4  # active / désactive l'éclairage dynamique
MENU_KEYS = {  # navigation dans les menus (flèches ou ZQSD)
    "up": (pygame.K_UP, pygame.K_z),
    "down": (pygame.K_DOWN, pygame.K_s),
    "left": (pygame.K_LEFT, pygame.K_q),
    "right": (pygame.K_RIGHT, pygame.K_d),
    "confirm": (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE),
    "back": (pygame.K_ESCAPE,),
}

# --- Joueur ------------------------------------------------------------------
PLAYER_SIZE = 22  # côté de la boîte de collision, en pixels (< TILE_SIZE)
PLAYER_SPEED = {"crouch": 75, "walk": 150, "run": 240}  # pixels / seconde
PLAYER_NOISE = {"crouch": 0, "walk": 96, "run": 224}  # rayon de bruit des pas, en pixels
FOOTSTEP_INTERVAL = {"walk": 0.42, "run": 0.27}  # secondes entre deux pas audibles
PLAYER_DETECTABILITY = {"crouch": 0.5, "walk": 1.0, "run": 1.5}  # multiplie la vitesse de détection par un garde

# --- Score et rangs ------------------------------------------------------------
# Score d'une mission = points de temps + points d'alerte + points de leurres (10 000 au maximum).
SCORE_TIME_MAX = 4000  # points si l'on finit dans le temps de référence de la mission (`par_time`)...
SCORE_TIME_PENALTY = 25  # ... moins ce nombre de points par seconde en trop
SCORE_ALERT_MAX = 4000  # points si aucune alerte n'a été déclenchée
SCORE_ALERT_PENALTY = 2000  # ... moins ce nombre de points par alerte
SCORE_DECOY_MAX = 2000  # points si aucun leurre n'a été utilisé
SCORE_DECOY_PENALTY = 500  # ... moins ce nombre de points par leurre
RANKS = (  # (lettre, nom, score minimum), du meilleur au moins bon
    ("S", "Fantôme", 9500),
    ("A", "Agent d'élite", 8000),
    ("B", "Infiltré", 6000),
    ("C", "Recrue", 3500),
    ("D", "Survivant", 0),
)

# --- Générique de mission ------------------------------------------------------
CRAWL_THEME = "generique"  # musique (assets/sounds/generique.wav) ; absente, le générique défile en silence
CRAWL_SKIP_KEYS = (pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE)  # à maintenir pour passer l'introduction
CRAWL_SKIP_HOLD = 1.0  # secondes à maintenir la touche
CRAWL_SPEED = 38.0  # vitesse de défilement (px/s) ; indépendante de la musique, qui s'éteint en fondu à la fin
CRAWL_STOP_SCALE = 0.35  # le défilement s'arrête quand la dernière ligne est réduite à cette échelle (1 = bas de l'écran)
CRAWL_PROLOGUE_TIME = 5.5  # secondes d'affichage de la phrase d'accroche bleue (si la mission en a une)
CRAWL_LOGO_TIME = 4.5  # secondes du titre qui s'éloigne, avant le texte
CRAWL_END_PAUSE = 1.2  # silence après la fin du texte

# --- Préférences et difficulté ----------------------------------------------
DEFAULT_VOLUMES = {"master": 0.8, "music": 0.6, "sfx": 0.9}
VOLUME_STEP = 0.1
DEFAULT_DIFFICULTY = "normal"
# detect : vitesse de détection des gardes ; lockdown : secondes avant verrouillage ;
# waves : vagues de renforts ; stay : secondes de présence d'un renfort.
DIFFICULTIES = {
    "easy": {"label": "Facile", "detect": 0.8, "lockdown": 210.0, "waves": 2, "stay": 18.0},
    "normal": {"label": "Normal", "detect": 1.0, "lockdown": 150.0, "waves": 3, "stay": 25.0},
    "hard": {"label": "Difficile", "detect": 1.2, "lockdown": 110.0, "waves": 4, "stay": 30.0},
}

# --- Audio -------------------------------------------------------------------
SOUND_RANGE = 520  # distance (px) au-delà de laquelle un son localisé (garde, porte, leurre) est inaudible
MIXER_CHANNELS = 24  # voix simultanées pour les effets (les 2 boucles de musique ont leurs propres voies)
MUSIC_CHANNELS = 2
TENSION_FADE_TIME = 1.5  # secondes pour passer de la musique calme à la musique tendue
DUCK_VOLUME = 0.35  # la musique baisse à ce niveau pendant la pause
HACK_TICK_INTERVAL = 0.28  # bips pendant un piratage
ALERT_LOOP_VOLUME = 0.5  # klaxon qui tourne en boucle pendant le verrouillage (par rapport aux autres effets)

# --- Décor -------------------------------------------------------------------
CONTAINER_PALETTE = ((74, 100, 124), (122, 88, 62), (78, 108, 86), (112, 112, 122), (110, 84, 112))  # coques des conteneurs
CONTAINER_STRIPES = ((255, 150, 60), (90, 180, 250), (120, 220, 130), (240, 205, 80))
FIELD_SCAN_SPEED = 90  # px/s : vitesse des impulsions qui parcourent le champ de force
FIELD_SCAN_SPACING = 70  # px entre deux impulsions
DOOR_OPEN_TIME = 0.4  # secondes que mettent les vantaux d'une porte à coulisser (purement visuel)
SPACE_PARALLAX = (0.08, 0.2, 0.4)  # profondeur des étoiles : plus c'est loin, moins elles bougent avec la caméra
SPACE_STAR_COUNT = 190

# --- Champs de force commutables et boutons -----------------------------------
LINK_COLOR_COUNT = 6  # nombre de teintes `link_N` dans COLORS (au-delà, on les réutilise)
BUTTON_REACH = TILE_SIZE  # distance (px) à laquelle on peut actionner un bouton : une tuile
BUTTON_COOLDOWN = 0.4  # délai anti-répétition entre deux pressions
FIELD_PENDING_BLINK = 5.0  # Hz : clignotement d'un champ qui attend que sa zone soit libre
FIELD_GATE_BAND = 12  # px : demi-épaisseur de la bande d'énergie d'un champ commutable actif

# --- Éclairage ---------------------------------------------------------------
LIGHTING_ENABLED = True  # au démarrage ; F4 le bascule en jeu
LIGHT_DOWNSCALE = 2  # la carte de lumière est calculée en demi-résolution, puis agrandie (adoucit les bords)
AMBIENT_LIGHT = (120, 132, 162)  # lumière de base : en dessous de 255, ce qui n'est pas éclairé s'assombrit
AMBIENT_ALARM = (170, 54, 62)  # teinte de l'ambiance pendant l'alerte globale
ALARM_FADE_TIME = 1.0  # secondes pour passer de l'ambiance calme à l'ambiance d'alerte
ALARM_PULSE_SPEED = 3.2  # rad/s : rythme des gyrophares
LAMP_SPACING = 8  # une lampe de plafond par bloc de cette taille (en tuiles), là où il y a de la place
LAMP_RADIUS = 200  # portée d'une lampe, en pixels
LAMP_RAYS = 72  # précision des ombres portées par les murs
LAMP_TINTS = ((190, 208, 255), (255, 228, 178), (186, 255, 226))  # une teinte par salle, pour la variété
LAMP_ALARM_COLOR = (255, 48, 48)
LAMP_FLICKER_ONE_IN = 8  # une lampe sur huit grésille
PLAYER_LIGHT = {"radius": 120, "color": (176, 204, 255), "intensity": 0.55}
GUARD_AURA = {"radius": 58, "color": (255, 196, 150), "intensity": 0.45}
GUARD_TORCH = {"color": (255, 240, 205), "alert_color": (255, 84, 84), "intensity": 0.6}  # lampe torche = cône de vision
SPOT_LIGHTS = {  # petites lueurs sans ombre : rayon (px), intensité
    "terminal": (72, 0.7),
    "console": (72, 0.7),
    "lantern": (88, 0.75),  # lanterne
    "exit": (92, 0.85),
    "door": (54, 0.6),
    "pickup": (48, 0.7),
    "gate": (92, 0.7),  # champ commutable actif (une lueur au centre de chaque ligne)
    "button": (40, 0.55),
    "field": (110, 0.8),  # champ de force : une lueur tous les FIELD_LIGHT_SPACING pixels
    "decoy": (104, 1.0),
}

# --- Objets et interactions --------------------------------------------------
MAX_BADGE_LEVEL = 3
DEFAULT_KEYCARD_LEVEL = 1  # niveau d'un `K` sans directive `@keycard`
DOOR_REACH = 52  # distance (px) à laquelle on peut actionner une porte (jusqu'à la tuile la plus proche)
TERMINAL_REACH = 40
EXIT_REACH = 44
HACK_TIME = 2.5  # secondes à maintenir E pour pirater un terminal
SHIP_RELEASE_TIME = 4.0  # secondes à maintenir E à la console pour libérer les vaisseaux (rayons tracteurs et attaches)
SHIP_RELEASE_NOISE = 240  # rayon (px) du bruit des attaches qui se libèrent
SHIP_RELEASE_FADE = 1.6  # secondes pour que les rayons s'éteignent et que les attaches s'ouvrent
POWER_CUT_TIME = 3.5  # secondes à maintenir E sur la console pour couper l'alimentation
POWER_CUT_NOISE = 260  # rayon (px) du bruit du disjoncteur : les gardes proches viennent voir
POWER_FADE_TIME = 1.4  # secondes pour que les lampes s'éteignent après la coupure
AMBIENT_BLACKOUT = (46, 54, 82)  # lumière de base une fois l'alimentation coupée
DOOR_NOISE = 80  # rayon de bruit d'une porte qui s'ouvre
PICKUP_SIZE = 16
PICKUP_RADIUS = 22  # distance (centre à centre) à partir de laquelle un objet est ramassé
THROW_RANGE = 240  # portée maximale d'un leurre
DECOY_NOISE = 260  # rayon de bruit de chaque bip du leurre
DECOY_BEEP_INTERVAL = 0.8
DECOY_DURATION = 5.0  # le leurre bipe pendant ce temps, puis s'éteint
DECOY_SIZE = 10
FIELD_LIGHT_SPACING = 160  # px entre deux lueurs le long d'un champ de force
TOAST_DURATION = 3.0  # durée d'affichage d'un message

# --- Alerte globale ----------------------------------------------------------
LOCKDOWN_TIME = 150.0  # secondes pour s'échapper une fois l'alerte donnée, sinon le croiseur est verrouillé
LOCKDOWN_WARNING_TIME = 20.0  # sous ce seuil, le chronomètre clignote
ALERT_RESPONDERS = 3  # nombre de gardes (les plus proches) prévenus par radio à chaque message
RADIO_INTERVAL = 3.0  # délai minimal entre deux messages radio tant qu'un garde voit le joueur
ALERT_DETECT_MULT = 1.5  # en alerte, les gardes repèrent le joueur plus vite
ALERT_SPEED_MULT = 1.25  # ... et patrouillent / enquêtent plus vite (la poursuite ne change pas)
REINFORCE_FIRST_DELAY = 12.0  # secondes entre l'alerte et la première vague
REINFORCE_INTERVAL = 35.0  # puis une vague toutes les ...
REINFORCE_PER_WAVE = 1
REINFORCE_WAVES = 3  # nombre total de vagues pendant une alerte
REINFORCE_MAX = 3  # renforts présents en même temps, au maximum
REINFORCE_STAY_TIME = 25.0  # un renfort se retire après ce temps (sauf s'il est en pleine poursuite)
REINFORCE_MIN_DISTANCE = 320  # un renfort n'apparaît pas à moins de 10 tuiles du joueur...
REINFORCE_HIDE_DISTANCE = 640  # ... ni à l'écran (en vue directe et à moins de cette distance)

# --- Gardes ------------------------------------------------------------------
GUARD_SIZE = 22
GUARD_SPEED = {"patrol": 70, "investigate": 110, "chase": 185}  # pixels / seconde (le joueur marche à 150, court à 240)
GUARD_VISION_RANGE = 224  # portée du cône de vision, en pixels
GUARD_FOV = math.radians(80)  # ouverture totale du cône
GUARD_VISION_RAYS = 28  # rayons lancés pour dessiner le cône (le détail visuel n'affecte pas la détection)
GUARD_TURN_SPEED = math.radians(300)  # rotation maximale, en radians / seconde
GUARD_DETECT_TIME = 1.0  # secondes pour repérer un joueur qui marche, à portée maximale
GUARD_DETECT_CLOSE_BONUS = 2.0  # à bout portant, la détection est (1 + bonus) fois plus rapide
GUARD_AWARENESS_DECAY = 0.4  # la méfiance retombe de cette fraction par seconde sans contact visuel
GUARD_AWARENESS_AFTER_CHASE = 0.5  # méfiance restante quand le garde abandonne la poursuite
GUARD_LOSE_SIGHT_TIME = 1.5  # secondes sans voir le joueur avant d'abandonner la poursuite
GUARD_CATCH_DISTANCE = 24  # distance (centre à centre) à laquelle un garde en poursuite attrape le joueur
GUARD_WAIT_TIME = 1.2  # pause à chaque point de patrouille
GUARD_SEARCH_TIME = 4.0  # durée de la fouille sur place après une enquête
GUARD_SEARCH_SWEEP = math.radians(70)  # amplitude du balayage du regard pendant la fouille
GUARD_REPATH_INTERVAL = 0.3  # délai minimal entre deux recalculs A* en poursuite
PATH_ARRIVE_TOLERANCE = 3.0  # distance (px) à partir de laquelle un point de chemin est atteint
HEARING_WALL_PENALTY = 48  # chaque tuile solide entre la source et le garde étouffe le bruit d'autant de pixels

# --- Caméra ------------------------------------------------------------------
CAMERA_SMOOTHING = 8.0  # plus grand = caméra plus nerveuse ; 0 = collée au joueur
CAMERA_LOOKAHEAD = 64  # px : de combien la caméra prend de l'avance dans le sens du déplacement (à pleine course)
CAMERA_LOOKAHEAD_SMOOTHING = 3.0  # rapidité avec laquelle cette avance s'installe ou se relâche (plus lent que le suivi)
CAMERA_AIM_LEAN = 0.14  # part de la distance curseur-centre dont la caméra se penche vers le curseur
CAMERA_AIM_MAX = 56  # px : inclinaison maximale vers le curseur
CAMERA_ZOOM_SMOOTHING = 2.6  # rapidité du zoom
CAMERA_ZOOM = {"crouch": 1.04, "chase": 1.07, "focus": 1.09, "caught": 1.16}  # zoom selon la situation (1 = normal)
CAMERA_SHAKE_MAX = 12  # px : amplitude d'une secousse à pleine intensité
CAMERA_SHAKE_SPEED = 38.0  # rad/s : vivacité de la secousse
CAMERA_TRAUMA_DECAY = 1.5  # intensité perdue par seconde (une secousse de 1 dure ~0,7 s)
CAMERA_ZOOM_EPS = 0.004  # sous ce zoom, on dessine sans mise à l'échelle (inutile et coûteuse)
SHAKE_EVENTS = {  # événement -> intensité (0..1) ; localisés : atténués avec la distance
    "alert_raised": 0.55,
    "ships_released": 0.5,
    "reinforcements_arrived": 0.3,
    "lockdown": 0.8,
    "player_caught": 0.9,
    "power_cut": 0.6,
}
SHAKE_FIELD = 0.28  # un champ de force qui bascule, entendu de près
SHAKE_DOOR = 0.14  # une porte qui s'ouvre, de près
SHAKE_RANGE = 380  # px : au-delà, une secousse localisée n'est plus ressentie
PAUSE_ZOOM = 0.05  # le fond flouté de la pause se rapproche lentement de cette part de son échelle
PAUSE_ZOOM_SPEED = 1.6  # rapidité de ce rapprochement

# --- Couleurs ----------------------------------------------------------------
COLORS = {
    "background": (8, 10, 16),
    "floor_a": (38, 44, 58),
    "floor_b": (34, 40, 53),
    "wall": (92, 100, 118),
    "wall_top": (128, 137, 156),
    "wall_shade": (58, 64, 78),
    "player_walk": (80, 170, 240),
    "player_run": (240, 190, 70),
    "player_crouch": (60, 120, 170),
    "player_outline": (10, 20, 35),
    "player_dir": (235, 245, 255),
    "shadow": (0, 0, 0),
    "guard_patrol": (176, 78, 88),
    "guard_investigate": (226, 146, 62),
    "guard_search": (226, 146, 62),
    "guard_chase": (250, 72, 72),
    "guard_visor": (20, 24, 36),
    "guard_reinforcement": (130, 150, 255),  # anneau qui distingue les renforts
    "guard_gun": (150, 156, 170),
    "armor_white": (232, 234, 242),  # armure des gardes
    "armor_shade": (178, 184, 200),
    "armor_under": (54, 58, 72),  # combinaison sous l'armure
    "sprite_skin": (222, 188, 160),
    "sprite_boot": (38, 44, 58),
    "sprite_helmet": (214, 220, 232),
    "sprite_glass": (70, 150, 210),
    "sprite_pack": (96, 84, 62),
    "sprite_stripe": (232, 128, 44),  # liseré orange du casque de l'agent rebelle
    "cone_patrol": (255, 236, 150),
    "cone_investigate": (255, 170, 60),
    "cone_search": (255, 170, 60),
    "cone_chase": (255, 66, 66),
    "camera_cone": (120, 200, 255),  # cône d'une caméra de surveillance qui ne voit rien
    "uniform": (128, 138, 130),  # uniforme impérial (tunique grise verdâtre)
    "uniform_cap": (58, 64, 70),
    "prisoner_suit": (236, 128, 40),  # combinaison du prisonnier
    "prisoner_cuff": (150, 156, 170),
    "cell_bars": (112, 122, 146),
    "alert_bubble": (12, 16, 28),
    "alert_glyph": (245, 240, 225),
    "status_calm": (90, 220, 120),
    "status_suspect": (255, 170, 60),
    "status_alert": (255, 70, 70),
    "alarm": (255, 40, 40),
    "debug_path": (90, 220, 255),
    "crate_body": (88, 94, 110),
    "crate_dark": (46, 50, 62),
    "crate_light": (142, 150, 168),
    "hazard_yellow": (232, 190, 50),
    "hazard_dark": (30, 32, 40),
    "ship_hull": (188, 196, 210),
    "ship_hull_dark": (112, 120, 138),
    "ship_panel": (74, 80, 96),
    "ship_glass": (74, 156, 206),
    "ship_engine": (130, 214, 255),
    "ship_accent": (206, 72, 72),
    "field_core": (150, 240, 255),
    "field_glow": (60, 170, 230),
    "field_deck": (30, 36, 50),
    "door_metal": (66, 74, 94),
    "door_metal_light": (112, 122, 146),
    "door_frame": (34, 38, 50),
    "door_locked": (255, 70, 70),
    "link_0": (90, 220, 255),  # champs commutables : une teinte par groupe bouton(s) + champ(s) liés (cyan par défaut)
    "link_1": (255, 176, 56),
    "link_2": (238, 98, 214),
    "link_3": (140, 232, 86),
    "link_4": (148, 128, 255),
    "link_5": (255, 108, 98),
    "rank_S": (255, 214, 90),
    "rank_A": (120, 232, 160),
    "rank_B": (110, 192, 255),
    "rank_C": (204, 204, 220),
    "rank_D": (180, 140, 118),
    "crawl_yellow": (255, 232, 31),
    "crawl_blue": (75, 213, 238),
    "badge_0": (110, 200, 235),
    "badge_1": (90, 210, 120),
    "badge_2": (240, 190, 70),
    "badge_3": (235, 90, 120),
    "door_open": (24, 28, 40),
    "item_data": (120, 190, 255),
    "item_decoy": (255, 150, 90),
    "item_body": (52, 58, 74),
    "terminal_body": (58, 66, 86),
    "terminal_screen": (80, 220, 230),
    "terminal_done": (90, 220, 120),
    "console_live": (255, 190, 70),
    "console_dead": (120, 130, 150),
    "exit_ready": (90, 220, 120),
    "exit_idle": (84, 96, 100),
    "panel": (12, 16, 28),
    "panel_border": (70, 80, 104),
    "debug_hitbox": (90, 255, 120),
    "debug_noise": (255, 160, 60),
    "debug_solid": (255, 70, 70),
    "text": (230, 235, 245),
    "text_dim": (150, 160, 180),
}

# --- Effets visuels (particules) ---
PARTICLE_LIMIT = 600  # plafond de particules vivantes (les nouvelles sont ignorées au-delà)
DUST_COLOR = (176, 166, 148)  # poussière de pas
SMOKE_COLOR = (118, 124, 140)  # fumée des moteurs
SPARK_COLORS = {"terminal": (120, 235, 255), "console": (255, 200, 90), "field": (150, 220, 255)}  # étincelles par genre de source
SPARK_RATE = (6.0, 26.0)  # étincelles par seconde pendant un piratage : au début, à la fin
SPARK_BURST = {"terminal": 22, "console": 34, "field": 6}  # gerbe à l'achèvement (ou à la bascule d'un champ)
SMOKE_RATE = 8.0  # volutes par seconde et par tuyère
SMOKE_RANGE = 700  # px : les moteurs hors de portée de la caméra ne fument pas
DUST_CHASE_INTERVAL = 0.16  # secondes entre deux nuages de poussière d'un garde qui court après le joueur
NOZZLE_SPACING = 3  # une tuyère de plus par tranche de cette largeur (en tuiles) de la poupe d'un vaisseau

# --- Commandes tactiles (version web sur téléphone ou tablette) ---
TOUCH_BUTTON_RADIUS = 38  # px
TOUCH_MARGIN = 14
TOUCH_STICK_RADIUS = 70  # px de course du pouce pour pousser le joystick à fond

# --- Acoustique : occlusion, réverbération, voix ---
OCCLUSION_VOLUME = 0.7  # part du volume qui franchit chaque mur ou porte fermée entre une source et le joueur
MUFFLE_CUTOFFS = (None, 1500, 800, 420)  # coupure (Hz) du filtre passe-bas selon le nombre de murs (0 = son net) ; au-delà : le dernier
REVERB_AREAS = (120, 450)  # surface (tuiles) de la zone connexe à partir de laquelle la salle résonne un peu, puis beaucoup
REVERB_TAPS = (  # niveau de réverbération -> échos (délai en s, part du volume) ajoutés à l'effet ; le niveau 0 n'ajoute rien
    (),
    ((0.045, 0.30), (0.09, 0.18), (0.14, 0.10)),
    ((0.06, 0.38), (0.12, 0.30), (0.19, 0.24), (0.27, 0.17), (0.36, 0.11), (0.47, 0.06)),
)
REVERB_MAX_SOUND = 5.0  # secondes : les sons plus longs (musiques, boucles) ne reçoivent ni écho ni filtre
VOICE_VOLUME = 0.9  # répliques des gardes (localisées : elles passent par les murs comme le reste)
RADIO_VOLUME = 0.6  # crachotements de radio, entendus où que l'on soit
VOICE_GAP = 1.6  # secondes minimum entre deux répliques, tous gardes confondus
VOICE_CATEGORY_COOLDOWN = 5.0  # secondes avant qu'une même catégorie (soupçon, poursuite...) reparle
VOICE_LINES = {"suspect": 3, "chase": 3, "lost": 2, "radio": 2}  # catégorie -> nombre de variantes (fichiers voice_<catégorie>_<n>.wav)

# --- Ambiances sonores localisées ---
# Genre de source -> (son en boucle, portée en px, volume). Un seul canal par son : les sources proches s'additionnent.
AMBIENT_SOURCES = {
    "engine": ("amb_engine", 440, 0.95),  # moteurs des vaisseaux (hangars)
    "lamp": ("amb_lamp", 250, 0.55),  # bourdonnement des lampes de plafond (une par salle : le « son de la salle »)
    "field": ("amb_field", 260, 0.7),  # champs de force
    "terminal": ("amb_terminal", 190, 0.6),  # terminal : petits bips tant qu'il n'est pas piraté
    "console": ("amb_console", 220, 0.7),  # console de la salle de contrôle : ronronnement de transformateur
}
AMBIENT_WALL_DAMPING = 0.45  # un mur ou une porte fermée entre la source et le joueur ne laisse passer que cette part du son
AMBIENT_FADE_RATE = 2.0  # variation maximale du volume par seconde : pas de saut quand on franchit une porte
AMBIENT_REFRESH = 0.1  # secondes entre deux recalculs des volumes (le lissage, lui, est à chaque image)
AMBIENT_FLOOR = 0.01  # sous ce volume, la boucle est arrêtée (on ne garde pas une voix muette)

# --- Décor vivant : lanternes murales, jets de vapeur, vent, poussière en suspension ---
DECOR_ONE_IN = 7  # une tuile de mur sur sept (parmi celles qui bordent un passage) porte une lanterne (si le thème en a)
DECOR_SPACING = 2  # écart minimal (en tuiles) entre deux éléments de décor mural
VENT_ONE_IN = 34  # une tuile de sol contre un mur sur trente-quatre est une bouche de vapeur
VENT_SPACING = 5  # écart minimal (en tuiles) entre deux bouches
VENT_START_CLEARANCE = 6  # les bouches restent à cette distance (en tuiles) du départ du joueur
VENT_PERIOD = (4.5, 8.0)  # secondes entre deux jets (varie d'une bouche à l'autre)
VENT_BURST = 1.7  # durée d'un jet
VENT_RATE = 24.0  # volutes par seconde pendant un jet
VENT_RANGE = 640  # px : les bouches hors de portée du joueur restent muettes et immobiles
WIND_GUST_SPEED = (0.35, 0.13)  # rad/s : les deux rythmes dont les rafales sont faites (leur produit varie de 0 à 1)
WIND_SAND_RATE = 46.0  # grains de sable par seconde à pleine rafale (thème avec vent de sable)
WIND_LEAF_RATE = 4.5  # feuilles par seconde (thème avec feuilles portées par le vent)
MOTE_RATE = 1.6  # grains de poussière en suspension par seconde et par lampe visible
MOTE_RADIUS = 96  # px : ils flottent dans le halo de la lampe
AMBIENT_PARTICLE_SHARE = 0.7  # part du plafond de particules que le décor peut occuper : les étincelles passent toujours

# --- Manette ---
GAMEPAD_DEADZONE = 0.25  # part de la course du joystick ignorée (dérive au repos)
GAMEPAD_TRIGGER = 0.45  # le gâchette droite compte comme appuyée au-delà de cette course
GAMEPAD_NAV_ON, GAMEPAD_NAV_OFF = 0.6, 0.3  # joystick dans les menus : seuils d'enclenchement et de relâchement (hystérésis)
GAMEPAD_AIM_RADIUS = 240  # px : à quelle distance du centre « pointe » le joystick droit (visée, inclinaison de la caméra)

# --- Éclairage et détection (B5) ---
LIGHT_FALLOFF = 1.6  # décroissance d'une lumière avec la distance : (1 - d/rayon) ** LIGHT_FALLOFF (rendu et détection)
VISIBILITY_FACTORS = (0.5, 1.25)  # multiplicateur de la détection du joueur : (dans le noir complet, en pleine lumière)
VISIBILITY_SHADOW_MARGIN = 0.06  # on est « dans l'ombre » quand aucune lumière n'ajoute plus que ça à la clarté ambiante de la carte
VISIBILITY_LIT_MARGIN = 0.25  # ... et « en pleine lumière » quand elles lui ajoutent au moins ça
LAMP_FADE_TIME = 0.8  # secondes pour qu'une lampe s'éteigne ou se rallume quand on coupe la lumière de sa salle

# --- Terminaux (B6) ---
TERMINAL_JOB_TIME = {"data": HACK_TIME, "cameras": 1.6, "lights": 1.6}  # secondes de connexion par action (rester près du terminal)
TERMINAL_LINK_RANGE = 78  # px : s'éloigner davantage coupe la connexion
LIGHTS_OUT_TIME = 25.0  # secondes pendant lesquelles la salle reste dans le noir
LIGHTS_OUT_NOISE = 170  # rayon (px) du claquement des disjoncteurs : les gardes proches viennent voir

# --- Caméras de surveillance (B1) ---
CAMERA_RANGE = 280  # portée du cône (px)
CAMERA_FOV = math.radians(56)  # ouverture totale du cône
CAMERA_SWEEP = math.radians(42)  # amplitude du balayage de chaque côté de l'axe (une carte peut en choisir une autre, en degrés)
CAMERA_SWEEP_PERIOD = 7.0  # secondes pour un aller-retour
CAMERA_DETECT_TIME = 1.3  # secondes pour repérer un joueur qui marche, à portée maximale (comme les gardes, avec la lumière en plus)
CAMERA_AWARENESS_DECAY = 0.6  # la méfiance retombe de cette part par seconde
CAMERA_ALARM_TIME = 5.0  # secondes pendant lesquelles une caméra qui a repéré le joueur reste sur lui (cône rouge)
CAMERA_RESPONDERS = 2  # nombre de gardes envoyés sur place quand une caméra repère le joueur
CAMERA_OFF_TIME = 40.0  # secondes de désactivation depuis un terminal
CAMERA_MOUNT = 0.62  # tuiles : la caméra voit depuis un point un peu en avant du mur qui la porte

# --- Sprites (personnages dessinés de dessus) ---
STRIDE_RATE = 0.19  # rad de cycle de marche par pixel parcouru : une foulée fait environ 33 px
STRIDE_BLEND = 10.0  # rapidité avec laquelle les jambes se figent à l'arrêt ou repartent (par seconde)
SPRITE_SWING = {"crouch": 4.5, "walk": 7.5, "run": 10.5}  # amplitude (px) du balancement des jambes et des bras selon la posture
SPRITE_BREATH = 0.9  # px : à l'arrêt, le torse se soulève doucement (respiration)
SPRITE_SIZE = 1.14  # agrandissement général des personnages par rapport à leur dessin de base
SPRITE_SCALE = {"crouch": 0.86, "walk": 1.0, "run": 1.0}  # accroupi : le personnage se tasse
SPRITE_LEAN = {"crouch": 2.0, "walk": 0.0, "run": 2.6}  # la tête se porte en avant en courant ou en rampant

# --- Prisonnier (objectif « libérer un prisonnier ») ---
PRISONER_REACH = 44  # px : distance à laquelle on peut le délivrer
PRISONER_FREE_TIME = 1.6  # secondes à maintenir E pour couper ses liens
PRISONER_SPEED = 150  # px/s : il suit à la vitesse de la marche
PRISONER_FOLLOW_DISTANCE = 52  # px : il s'arrête à cette distance du joueur
PRISONER_REPATH = 0.45  # secondes entre deux recalculs de son chemin
PRISONER_EXIT_RANGE = 110  # px : il doit être aussi près de la zone d'extraction pour qu'on parte avec lui
PRISONER_SIZE = 20
PRISONER_NOISE = 120  # rayon (px) du bruit des liens qui cèdent
CELLS_OPEN_NOISE = 200  # rayon (px) du bruit de toutes les cellules qui s'ouvrent depuis un terminal
TERMINAL_JOB_TIME["cells"] = 1.6

# --- Uniforme et déguisement ---
LOCKER_REACH = 40  # px : distance à laquelle on fouille un casier
LOCKER_TIME = 2.2  # secondes à maintenir E pour fouiller le casier
LOCKER_NOISE = 100  # rayon (px) du bruit des charnières
DISGUISE_RANGE = 72  # px : en uniforme, on ne passe pour un des leurs qu'au-delà de cette distance d'un garde (un peu plus de deux tuiles)
DISGUISE_CLOSE_FACTOR = 0.3  # ... en deçà, un garde regarde de près : il se méfie à ce rythme (par rapport à l'infiltration classique)
