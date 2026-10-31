# Star Infiltration

Jeu d'infiltration 2D en vue de dessus, en Python (pygame-ce) : un agent rebelle s'infiltre dans un croiseur impérial.

> Projet de loisir inspiré de l'univers Star Wars. Pour une publication, remplacer les noms, sprites et sons par des créations originales.

## Lancer le jeu

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

Le jeu s'ouvre sur un **menu principal** : *Campagne*, *Réglages*, *Quitter*. La campagne enchaîne douze missions de plus en plus difficiles, de l'*Entraînement* (un petit niveau pour découvrir les mécaniques, une par salle) jusqu'au *Destroyer*.

## Commandes

| Action | Touches |
|---|---|
| Se déplacer | Z Q S D ou flèches (clavier AZERTY) |
| Courir (bruyant : les gardes entendent de loin) | Maj |
| S'accroupir (silencieux, plus difficile à repérer) | Ctrl ou C |
| Interagir : ouvrir une porte, utiliser un terminal (ouvre son menu), extraction (appui) ; couper l'alimentation à la console (maintenir) | E |
| Lancer un leurre sonore vers la souris | F |
| Enfiler / retirer l'uniforme dérobé (touche remappable) | U |
| Viser | Souris |
| Mode debug (hitbox, rayon de bruit, tuiles solides, chemins A* et états des gardes) | F3 |
| Recommencer après une capture | R |
| Activer / désactiver l'éclairage dynamique | F4 |
| Pause (reprendre, recommencer, réglages, menu principal) | Échap (ou perte de focus de la fenêtre) |
| Menus | Flèches ou ZQSD, Entrée, Échap pour revenir, souris |

Ces touches sont les touches par défaut : **Réglages > Commandes** permet de remapper les actions de jeu (voir ci-dessous) et règle la manette. L'écran de jeu n'affiche plus de pense-bête permanent : l'entraînement donne des **astuces contextuelles** au moment où elles servent, avec les touches réellement utilisées (le rappel des commandes reste sur l'écran de pause).

### Remapper les touches

Dans **Réglages > Commandes**, chaque action (avancer, reculer, aller à gauche / à droite, courir, s'accroupir, interagir, lancer un leurre) a **deux emplacements de touche**. Gauche / droite choisit l'emplacement (celui entre crochets), **Entrée** le change (puis appuyez sur la nouvelle touche, Échap annule), **Suppr** le vide (une action garde toujours au moins une touche). Si la touche était déjà prise par une autre action, les deux **échangent** leurs touches ; Échap, R, F3 et F4 sont réservées. « Rétablir les touches par défaut » remet tout à zéro. Les touches sont enregistrées dans `preferences.json` par leur nom (`"keys"`) ; une valeur illisible retombe sur la touche par défaut.

### Manette

Une manette branchée (même à chaud) est reconnue automatiquement ; « Utiliser la manette » la désactive. Disposition (noms des boutons façon Xbox, la norme SDL adapte les autres marques) :

| Action | Manette |
|---|---|
| Se déplacer | joystick gauche (analogique : pousser doucement avance doucement) ou croix |
| Viser (leurre, inclinaison de la caméra) | joystick droit |
| Courir | RT ou RB |
| S'accroupir | B ou clic du joystick gauche |
| Interagir / pirater (maintenir) | A |
| Lancer un leurre | X |
| Enfiler / retirer l'uniforme | LB |
| Recommencer | Y |
| Pause | Start |
| Menus | croix ou joystick gauche, A pour valider, B pour revenir |

Les invites et les astuces parlent de boutons (« A », « Start ») dès qu'on joue à la manette, et de touches dès qu'on retouche au clavier ou à la souris. Maintenir A, B ou Start passe le générique.

## Réglages

Dans le menu principal ou la pause : volume général, musique, effets sonores, éclairage dynamique, secousses de l'écran, plein écran, difficulté, et l'écran **Commandes** (touches et manette). Ils sont enregistrés dès qu'on les change dans `~/.star-infiltration/preferences.json` (dossier modifiable avec la variable d'environnement `STAR_INFILTRATION_HOME`). Un fichier absent ou abîmé est simplement ignoré.

| Difficulté | Détection des gardes | Verrouillage | Vagues de renforts | Présence d'un renfort |
|---|---|---|---|---|
| Facile | ×0,8 | 210 s | 2 | 18 s |
| Normal | ×1 | 150 s | 3 | 25 s |
| Difficile | ×1,2 | 110 s | 4 | 30 s |

La difficulté s'applique au démarrage de la mission suivante (ou à *Recommencer*).

## Campagne, score et rangs

**Carte de la campagne.** Chaque mission est un nœud sur un chemin : verrouillée (cadenas), disponible (couronne qui pulse) ou terminée (la lettre du meilleur rang obtenu). Le panneau du bas détaille la mission choisie : résumé, temps de référence, meilleur score, meilleur temps, nombre de réussites, et l'échelle des rangs (obtenu, encore à viser, ou dépassé ; cachée tant que la mission est verrouillée). On se déplace avec les flèches ou ZQSD, Entrée ou un second clic lance, Échap revient au menu. Une mission se débloque en terminant la précédente.

**Générique.** Chaque lancement de mission commence par un texte défilant façon « il y a longtemps » : phrase d'accroche bleue (première mission), titre qui s'éloigne, puis le contexte de la mission qui défile en perspective sur les étoiles, avec la musique `generique.wav`. Le texte s'arrête quand sa dernière ligne s'est bien éloignée, sans attendre la fin de la musique (qui s'éteint en fondu). **Maintenez Espace, Entrée ou Échap une seconde pour passer l'introduction.** Sans le fichier, le texte défile en silence.

**Écran de fin de mission.** Il affiche le temps, les alertes déclenchées et les leurres utilisés avec les points de chacun, le score, le rang (S à D) et les distinctions de la partie (première réussite, nouveau record, meilleur temps, nouveau rang). Il propose la mission suivante, de rejouer, la carte de la campagne ou le menu principal.

**Score (sur 10 000) et rangs.** Le temps rapporte jusqu'à 4 000 points (le plein dans le temps de référence de la mission, puis −25 points par seconde en trop), l'absence d'alerte 4 000 (−2 000 par alerte), l'absence de leurre 2 000 (−500 par leurre).

| Rang | Nom | Score minimum |
|---|---|---|
| S | Fantôme | 9 500 (par exemple : dans le temps, sans alerte, un seul leurre) |
| A | Agent d'élite | 8 000 |
| B | Infiltré | 6 000 |
| C | Recrue | 3 500 |
| D | Survivant | 0 |

**Sauvegarde.** La progression (missions terminées, meilleur score, meilleur rang, meilleur temps, nombre de réussites) est enregistrée dès la fin d'une mission dans `progress.json`, à côté des préférences (`~/.star-infiltration/`). On garde le meilleur score et le meilleur temps séparément : une mauvaise partie ne les abaisse jamais. Un fichier absent ou abîmé est ignoré.

**Ajouter une mission.** Tout est dans `assets/campaign.json` : identifiant, titre, fichier de carte, temps de référence (`par_time`, en secondes), résumé, numéro d'épisode, paragraphes du générique et, facultativement, une phrase d'accroche, l'objectif (`"objective"` : `steal_plans`, par défaut, ou `cut_power`) et la menace (`"danger"`, de 1 à 5, affichée sur la carte). Les erreurs de ce fichier sont expliquées en français au démarrage.

## Les douze missions

La campagne monte en difficulté : chaque niveau a plus de gardes, de portes, de champs de force et de caméras que le précédent, et introduit une nouveauté à la fois (`tests/test_campaign_levels.py` le vérifie avec un indice de complexité, `level_check.complexity`).

| # | Mission | Thème | Objectif | Menace | Taille | Gardes | Ce qu'on y apprend |
|---|---|---|---|---|---|---|---|
| 1 | Entraînement | vaisseau | voler les plans | 1 | 51 × 12 | 1 | les gestes de base (voir ci-dessous) |
| 2 | Avant-poste de Tatooine | Tatooine | voler les plans | 2 | 40 × 22 | 3 | **une caméra** et le terminal qui la coupe |
| 3 | Coupure de courant | Tatooine | couper l'alimentation | 2 | 50 × 26 | 7 | la console, deux badges, le noir qui aide |
| 4 | Le bunker d'Endor | Endor | voler les plans | 3 | 44 × 28 | 7 | un champ de force à ouvrir, un terminal de service |
| 5 | **Le vestiaire impérial** | vaisseau | **dérober un uniforme** | 3 | 52 × 30 | 8 | fouiller un casier, deux caméras, un champ à ouvrir, deux badges |
| 6 | Le poste radar d'Endor | Endor | couper l'alimentation | 3 | 56 × 30 | 9 | deux champs, trois caméras, deux terminaux de service |
| 7 | **Le centre de détention** | Tatooine | **libérer un prisonnier** | 4 | 60 × 34 | 9 | cellules à barreaux, terminal « cellules », un compagnon à escorter |
| 8 | Le hangar de la flotte | vaisseau | voler les plans | 4 | 64 × 38 | 10 | **trois niveaux de badge**, vaisseaux, baie sur l'espace, cloison |
| 9 | **Vol de la navette** | vaisseau | **voler un vaisseau** | 4 | 64 × 40 | 12 | rayons tracteurs et attaches, console de libération, embarquement |
| 10 | **Le quartier général** | vaisseau | voler les plans **en uniforme** | 4 | 60 × 40 | 14 | **porte du personnel** : seul l'uniforme passe le contrôle, l'infiltration classique est impossible |
| 11 | Le croiseur impérial | vaisseau | voler les plans | 4 | 72 × 48 | 14 | tout mélangé, grande carte |
| 12 | Le Destroyer | vaisseau | couper l'alimentation | 5 | 80 × 50 | 17 | cinq caméras, trois terminaux de service, réacteur à atteindre |

Les missions se débloquent dans cet ordre. Pour en ajouter une : dessiner la carte (`assets/maps/`), la vérifier avec `check_level`, ajouter une entrée dans `campaign.json` (les tests exigent un temps de référence cohérent et que la complexité reste croissante).

## L'entraînement

Cinq salles alignées, de gauche à droite, avec **une découverte par salle** et un seul garde :

1. **Se déplacer** entre des caisses ; marcher sur le leurre (`L`) le ramasse.
2. **Une porte libre** (appuyer sur E près d'elle), puis un **badge** posé au sol.
3. **Une porte à badge** (les voyants disent le niveau requis), puis un **bouton** : E pour ouvrir le champ de force qui barre la sortie de la salle.
4. **Un garde** qui patrouille : rester hors de son cône, se cacher derrière les caisses ou lancer le leurre (F).
5. **Le terminal** (E ouvre son menu, « Télécharger les données », puis rester près de lui), puis **la sortie**.

Pas de renforts ni de vaisseaux : on apprend sans rien de compliqué. La mission principale, elle, mélange tout.

## Le croiseur impérial (mission 7)

Mission : atteindre le poste de commandement (nord-est), pirater le terminal, puis fuir par le quai d'amarrage (sud-est).

- **Progression** : badge 1 (ingénierie) → badge 2 (casernes) → badge 3 (quartiers des officiers) → porte du poste de commandement.
- **Itinéraires** : une coursive centrale relie toutes les salles, mais elle est bien gardée ; deux tunnels de service relient les salles du sud sans la traverser, et les salles du nord communiquent entre elles par des portes.
- **Cachettes** : les couloirs d'accès aux salles sont des culs-de-sac où l'on peut laisser passer un garde ; des piliers coupent les lignes de vue de la coursive ; les leurres détournent les gardes.
- Le départ est sûr : aucun garde ne voit le joueur au début, et le plus proche en est à plus de 10 tuiles.

## Tests

```bash
pytest
```

Les tests ne touchent jamais à vos préférences ni à votre carte son (dossier temporaire, pilotes SDL factices).

## Sons

Les sons sont des fichiers WAV dans `assets/sounds/`, que l'on peut remplacer librement : il suffit de garder les noms. Un fichier manquant ou illisible est ignoré (signalé une fois dans les journaux), le jeu continue sans ce son.

| Fichiers | Usage |
|---|---|
| `step_walk` | pas du joueur (volume plus fort en courant, voir `STEP_SOUNDS` dans `sound_director.py`) |
| `door_open`, `door_denied` | porte ouverte / action refusée |
| `pickup`, `hack_tick`, `hack_done` | objet ramassé, piratage (bip répété, fin) |
| `decoy_throw`, `decoy_beep` | leurre lancé / bip du leurre |
| `suspect`, `spotted` | un garde se méfie / repère le joueur |
| `alert` | klaxon, **joué en boucle** pendant le verrouillage (prévoir un son qui boucle proprement) |
| `reinforcements`, `lockdown`, `caught`, `win` | renforts, verrouillage, capture, victoire |
| `generique` | musique du générique de mission (facultatif : sans le fichier, le texte défile en silence) |
| `amb_engine`, `amb_lamp`, `amb_field`, `amb_terminal`, `amb_console` | **ambiances en boucle**, une par genre de source (voir ci-dessous) : moteurs des vaisseaux, bourdonnement des lampes, champs de force, bips d'un terminal, ronronnement de la console. Elles doivent boucler proprement |
| `button_press`, `field_on`, `field_off` | bouton actionné, champ de force qui s'allume / s'éteint (entendus depuis leur position) |
| `power_down` | l'alimentation est coupée (toute la coque l'entend) |
| `steam_vent` | un jet de vapeur s'ouvre (entendu depuis la bouche) |
| `tractor_off`, `cell_open` | rayons tracteurs et attaches libérés ; cellules ouvertes depuis un terminal |
| `voice_suspect_1`–`3`, `voice_chase_1`–`3`, `voice_lost_1`–`2` | répliques des gardes (soupçon, repérage, piste perdue), localisées |
| `voice_radio_1`–`2` | radio des gardes à l'alerte, aux renforts et quand une caméra repère le joueur (partout audible) |
| `locker_open`, `disguise` | casier d'officier fouillé ; uniforme enfilé ou retiré |
| `terminal_open`, `camera_off`, `lights_out` | menu d'un terminal, caméras désactivées, lumière d'une salle coupée (une caméra qui repère le joueur réutilise `spotted`) |
| `ui_move`, `ui_select`, `ui_back` | menus |
| `music_ambient`, `music_tension` | deux musiques **en boucle** ; `music_ambient` joue en permanence |

Effets (pas, portes, objets, piratage, leurres, alerte, renforts, verrouillage, victoire, capture, interface) et deux boucles de musique : la musique normale joue en permanence, et une couche plus tendue s'y mêle légèrement quand un garde enquête. Pendant le verrouillage, la musique reste la musique normale et le klaxon d'alerte tourne en boucle (il se tait en pause). Les sons localisés (portes, gardes, leurres) s'atténuent avec la distance et se balancent à gauche ou à droite. Sans périphérique audio, le jeu tourne en silence.

### Ambiances des salles

Chaque salle a son bruit de fond, qui vient de ce qu'elle contient et qui se mélange selon la position du joueur (`game/systems/ambience.py`, réglages dans `AMBIENT_SOURCES` de `settings.py`) :

| Source | Son | Particularité |
|---|---|---|
| vaisseaux (hangars) | `amb_engine` | grave, audible de loin |
| lampes de plafond (une par salle) | `amb_lamp` | **se tait quand l'alimentation est coupée** |
| champs de force | `amb_field` | seulement tant qu'ils sont actifs |
| terminal | `amb_terminal` | se tait une fois piraté |
| console de contrôle | `amb_console` | se tait une fois l'alimentation coupée |

Les sources d'un même genre se mélangent en une seule voix (volume = somme, borné), le son penche du côté des plus proches, **un mur ou une porte fermée l'étouffe de moitié environ** (`AMBIENT_WALL_DAMPING`) et le volume varie en douceur quand on change de pièce. Les ambiances se taisent en pause et à la sortie de la mission. Les sons fournis sont **provisoires** : remplacez les WAV en gardant les noms (et des boucles qui se raccordent sans clic).

## Thèmes visuels

Chaque carte a un thème, choisi par la directive `@theme nom` (le vaisseau impérial si elle est absente). Un thème donne la palette du sol et des murs, leur texture, la lumière ambiante, la teinte des lampes et la couleur de la poussière (`game/world/themes.py`, dessin dans `tile_art.py`).

| Thème | `@theme` | Ambiance | Mission |
|---|---|---|---|
| Vaisseau impérial | `imperial` (défaut) | tôle grise, lumière froide | Entraînement, Le croiseur impérial |
| Base terrestre de Tatooine | `tatooine` | sable et murs de pisé, lumière chaude et claire | Coupure de courant |
| Base terrestre d'Endor | `endor` | sol de forêt et rondins moussus, nuit verdâtre | Le bunker d'Endor |

Les caisses, portes, vaisseaux et champs de force gardent leur aspect commun à tous les thèmes. Pour un nouveau thème : une entrée dans `themes.py` (et, si on veut une texture neuve, un style dans `tile_art.py`).

## Caméra

La caméra est plus expressive (`game/core/camera.py`, réglages `CAMERA_*` et `SHAKE_*` de `settings.py`) :

- **Avance** dans le sens du déplacement (jusqu'à 64 px en courant), qui s'installe et se relâche en douceur.
- **Inclinaison vers le curseur** (légère, plafonnée), seulement quand la souris est dans la fenêtre.
- **Zoom lissé, centré sur le joueur** (même au bord de la carte, où la caméra ne peut pas le centrer : il ne sort jamais de l'écran) selon la situation : accroupi (léger), poursuite ou alerte, piratage ou coupure (focus), capture (le plus serré). L'invite et le visée de la souris restent justes. Le fond de la pause se rapproche lentement.
- **Secousses** : alerte, renforts, verrouillage, capture, coupure de courant, et de près une porte qui s'ouvre ou un champ de force qui bascule. Désactivables dans les réglages (« Secousses de l'écran »).

## Vaisseaux

Les vaisseaux (`S`) sont dessinés par code (`game/world/prop_art.py`) : une **navette** (au-delà de 3 × 3 tuiles) à fuselage ombré, ailes en flèche armées, dôme radar, verrière à reflets et trois tuyères à capot, et un **chasseur** (jusqu'à 3 × 3) à nacelle sphérique armée entre deux panneaux hexagonaux. Une ombre portée en forme de coque tombe toujours vers le bas à droite, quel que soit le sens du nez ; les lampes **survolent** les vaisseaux (ils ne projettent pas l'ombre d'un rectangle plein) mais ils arrêtent toujours le regard des gardes. Les vaisseaux posés restent vivants : la lueur de leurs moteurs pulse (chacun à son rythme) et leurs feux de position clignotent, rouge à bâbord et vert à tribord, du bon côté quelle que soit l'orientation `@ship`. Le sprite est mis en cache ; seules la lueur et les feux sont redessinés à chaque image.

## Personnages

L'agent rebelle et les gardes impériaux sont dessinés par code, de dessus (`game/ui/sprites.py`, aucune image à fournir) : épaules, bras, jambes, sac et casque, ombre portée, tournés vers là où ils regardent.

- **Marche animée** : jambes et bras se balancent avec la distance réellement parcourue (le personnage ne piétine pas contre un mur) et se figent en douceur à l'arrêt, où le torse respire.
- **Postures du joueur** : accroupi, il se tasse et se tient près du sol ; en course, il se penche en avant et balance plus large. La couleur du gilet suit la posture (bleu, ambre, bleu sombre).
- **Gardes** : armure blanche, visière sombre, fusil à deux mains. Le liseré dans le dos, les épaulettes et l'œil de la visière reprennent la couleur de l'état d'alerte (patrouille, enquête, poursuite) ; en poursuite le garde épaule son fusil. Les renforts ont une bande bleue sur le casque, en plus de leur anneau.

## Décor vivant

Le décor bouge de lui-même, sans rien écrire dans les cartes : tout est placé automatiquement et de façon déterministe (`game/world/decor.py`), selon le thème, et ne bloque jamais ni le passage ni la vue.

| Élément | Où | Détail |
|---|---|---|
| **Lanternes** | murs de Tatooine et d'Endor | flamme qui vacille et éclaire un peu le passage, **brûlent même quand le courant est coupé** |
| **Bouches de vapeur** | sol du vaisseau impérial (vapeur) et d'Endor (brume) | un jet de ~1,7 s toutes les 4,5 à 8 s, avec son (`steam_vent`), seulement près du joueur |
| **Vent** | Tatooine (grains de sable, par rafales), Endor (feuilles qui tombent en se balançant) | généré seulement dans la zone visible |
| **Poussière en suspension** | dans le halo de chaque lampe (s'arrête quand le courant est coupé) | grains lumineux presque immobiles |

Le décor ne peut occuper que 70 % du plafond de particules (`AMBIENT_PARTICLE_SHARE`) : les étincelles et la fumée passent toujours. Réglages (densité, rythme, portée) à la fin de `settings.py`, couleurs par thème dans `themes.py`.

## Effets visuels

Des particules animent la carte (`game/ui/particles.py`, déclenchées par `game/systems/effects.py`, réglages en fin de `settings.py`) : **poussière** sous les pas (plus forte en courant, aussi derrière un garde qui poursuit le joueur), **étincelles** pendant un piratage (de plus en plus nombreuses) et en gerbe quand il se termine, quand un champ de force bascule ou que l'alimentation est coupée, **fumée** à la poupe des vaisseaux (seulement près du joueur). La poussière et la fumée sont assombries avec le décor ; les étincelles sont dessinées après l'éclairage et brillent dans le noir. Le nombre de particules est plafonné (`PARTICLE_LIMIT`).

## Empaquetage

Plusieurs façons de livrer le jeu, pilotées par `python packaging/build.py <cible>` (résultats dans `dist/`, ignoré par git) :

| Cible | Ce que ça produit | Pré-requis |
|---|---|---|
| `zip` | archive **portable des sources** : le jeu, `requirements.txt` et des lanceurs `run.sh` / `run.bat` qui créent leur environnement virtuel au premier lancement | Python (pour lancer) |
| `exe` | **exécutable sans Python** (PyInstaller) pour le système sur lequel on lance la commande : Windows, macOS (`.app`) ou Linux ; dossier zippé `star-infiltration-<version>-<système>.zip` | `pip install -r requirements-build.txt` |
| `dmg` | **image disque macOS** (`star-infiltration-<version>-macos-<arch>.dmg`) : le `.app` et un raccourci vers Applications (glisser-déposer) | macOS (`hdiutil`) |
| `installer` | **installateur Windows** `star-infiltration-<version>-windows-x64-setup.exe` (Inno Setup) : dossier de programme au choix, raccourcis du menu Démarrer et du bureau, désinstallation | Windows, `iscc` (`choco install innosetup`) |
| `appimage` | **AppImage Linux** : un seul fichier exécutable, sans installation | Linux, `appimagetool` dans le PATH (ou variable `APPIMAGETOOL`) |
| `web` | **version navigateur** (pygbag, WebAssembly) à déposer sur n'importe quel hébergement statique ; elle écarte la musique du générique (15 Mo, `--full` la garde) et convertit les sons en `.ogg` (pygbag refuse les `.wav` : le jeu sait lire les deux) | `pygbag`, `ffmpeg` (`--strict` échoue sans lui ; sans l'option, les `.wav` sont gardés avec un avertissement), une connexion Internet |
| `all` | `zip`, `exe` et `web` | |

Un exécutable ne se compile pas pour un autre système : le workflow `.github/workflows/build.yml` lance **ruff**, les tests, puis construit sur chaque système l'exécutable **et son installateur**, la version web (**vérifiée dans Chromium**, voir plus bas) et l'archive des sources, et publie le tout dans une release quand on pousse un tag `v1.2.3`.

Options de l'exécutable (et de `python main.py`) : `--version`, `--check` (contrôle la campagne, toutes les cartes et les sons **sans ouvrir de fenêtre** : bon test de fumée après une construction, code de sortie 1 en cas de problème), `--portable` (préférences et progression dans un dossier `data/` à côté du jeu, pour une clé USB) et `--dev` (mode développeur, absent des exécutables). Le numéro de version est `VERSION` dans `game/settings.py`. Les chemins des ressources passent par `settings.resource_root()`, qui retrouve les fichiers dans un exécutable figé.

### Icône et métadonnées

L'icône est **dessinée par le code** (`packaging/icons.py`, `python packaging/icons.py` la régénère) et écrite en PNG, `.ico` et `.icns` dans `packaging/icons/`, plus `assets/icon.png` pour la fenêtre du jeu. Toutes les métadonnées sont dans `packaging/metadata.py` (nom, éditeur, copyright, identifiant, catégorie) : propriétés du fichier sous Windows (éditeur, version, copyright), `Info.plist` macOS (version, catégorie « jeux d'action », système minimal), fichier `.desktop` Linux. Le `.spec` PyInstaller n'a plus rien à tenir à jour.

### Signature et notarisation

Rien n'est signé tant qu'aucun identifiant n'est défini : on obtient alors des livrables fonctionnels mais que le système signale au premier lancement. Avec les variables d'environnement suivantes (en CI : secrets du dépôt, voir l'en-tête du workflow), `build.py` signe et notarise tout seul :

| Système | Variables | Effet |
|---|---|---|
| macOS | `CODESIGN_IDENTITY` (« Developer ID Application: … ») | signe le `.app` et le `.dmg` (runtime durci, `packaging/entitlements.plist`) |
| macOS | `NOTARY_PROFILE`, ou `APPLE_ID` + `APPLE_TEAM_ID` + `APPLE_APP_PASSWORD` | notarise le `.dmg` (`notarytool --wait`) puis agrafe le ticket |
| Windows | `WINDOWS_CERT_FILE` (`.pfx`) + `WINDOWS_CERT_PASSWORD` | signe l'`.exe` et l'installateur (`signtool`, horodatage `WINDOWS_TIMESTAMP_URL`) |

Les commandes sont construites par des fonctions pures (`packaging/signing.py`) et testées ; la signature elle-même n'a pu être essayée qu'avec l'identité ad hoc de macOS (`CODESIGN_IDENTITY=-`), pas avec de vrais certificats ni avec la notarisation d'Apple.

### Version web

La CI installe `ffmpeg` (sons en `.ogg`, `--strict`), construit avec pygbag, puis **ouvre le résultat dans Chromium** (`packaging/web/smoke.py`, Playwright) : la page doit charger, le jeu démarrer et la console du navigateur ne montrer aucune erreur Python ; une capture d'écran est publiée avec la construction. Sur téléphone ou tablette, des **commandes tactiles** apparaissent dès qu'un doigt touche l'écran (`game/core/touch.py`) : un joystick virtuel là où le pouce gauche se pose, et à droite les boutons E (interagir, maintenu), COURIR et BAS (maintenus), F (leurre), U (uniforme), pause et R. Les menus se touchent comme à la souris.

### Linter

`ruff check .` (configuration dans `ruff.toml` : erreurs pyflakes/pycodestyle, ordre des imports, bogues probables) doit passer ; la CI le lance avant les tests, et `tests/test_distribution.py` le vérifie aussi quand ruff est installé (`pip install -r requirements-dev.txt`).

## Structure

```
star-infiltration/
├── main.py                  # point d'entrée
├── game/
│   ├── settings.py          # constantes : touches, couleurs, vitesses
│   ├── core/                # boucle de jeu, scènes, entrées, caméra, bus d'événements, audio, préférences
│   ├── difficulty.py        # niveaux de difficulté
│   ├── scenes/              # PlayScene (la partie), menu principal, pause, réglages, carte de la campagne, générique, résultats
│   ├── campaign.py          # Campaign, Mission, déblocage, échelle des rangs (données : assets/campaign.json)
│   ├── progress.py          # statistiques d'une mission, score, rang, progression sauvegardée
│   ├── items.py             # Item, Inventory (logique pure)
│   ├── entities/            # Entity (base), Player, Door, Terminal, PowerConsole, ExitPad, Pickup, Decoy
│   ├── systems/             # InteractionSystem (portes, terminaux, sortie, ramassage), AlertSystem (alerte, renforts, chronomètre), SoundDirector (événements → sons), Ambience (bruits de fond localisés), Effects (particules)
│   ├── world/               # Tilemap (chargement + rendu), collision (AABB), raycast (DDA), props / prop_art (caisses, vaisseaux, champs de force), lights (lampes, scintillement, ombres), level_check (faisabilité d'une carte)
│   ├── ai/                  # Guard (états), pathfinding A*, perception (vue/ouïe), steering
│   └── ui/                  # HUD (inventaire, invites, messages), icônes, WorldOverlay (cônes, bulles d'alerte), Lighting (éclairage), particules, menus (éléments, vue), fonds, crawl (générique en perspective)
├── assets/
│   ├── campaign.json        # la liste des missions, leurs textes de générique et temps de référence
│   ├── maps/                # huit cartes : training, outpost, blackout, endor, radar, hangar, cruiser, destroyer
│   │   └── cruiser.txt      # le niveau principal (72 x 48)
│   └── sounds/              # sons et musiques (WAV)
└── tests/                   # tests ; data/sandbox.txt est une grande carte de test, indépendante des niveaux livrés
```

## Format des cartes

Fichier texte, une ligne par rangée de tuiles (voir `assets/maps/cruiser.txt`). Une carte est vérifiée par `game.world.level_check.check_level` (les tests le font pour les cartes livrées) :

| Caractère | Signification |
|---|---|
| `#` | mur |
| `.` | sol |
| `D` | porte (solide tant qu'elle est fermée ; une porte double compte pour une seule porte) |
| `B` | caisse ou conteneur (les `B` contigus forment un seul conteneur) |
| `S` | vaisseau : un rectangle plein de `S` (chasseur jusqu'à 3 × 3 tuiles, navette au-delà) |
| `F` | champ de force **permanent** (baies d'amarrage) : une ligne droite d'une tuile d'épaisseur |
| `a`–`z` | champ de force **commutable** (toutes les tuiles de même lettre = un seul champ) |
| `1`–`9` | bouton (le sol est dessous) |
| `U` | casier d'officier : on y dérobe un uniforme impérial (maintenir `E`) ; `@door x,y -> uniform` fait de la porte une **porte du personnel** |
| (espace) | le vide de l'espace, avec des étoiles |
| `P` | départ du joueur |
| `G` | garde |
| `K` / `T` / `E` / `L` | badge / terminal / sortie / leurre sonore |
| `C` | console de la salle de contrôle (objectifs « couper l'alimentation » et « voler un vaisseau » : voir `@objective`) |
| `Q` | le prisonnier à libérer (objectif « libérer un prisonnier ») |
| `H` | **barreaux** de cellule : solides mais transparents (on voit et on éclaire à travers) |
| `J` | **porte de cellule** : une porte à barreaux, verrouillée électroniquement (un terminal « cellules » l'ouvre) sauf si `@door x,y -> n` lui donne un badge |
| `R` | point d'arrivée des renforts |

Les lignes commençant par `;` sont des commentaires. Directive `@theme nom` : aspect de la carte (voir « Thèmes visuels »).

### Réglages par carte

Chaque carte peut régler son propre équilibrage, sans toucher au code. Les valeurs valent **pour la difficulté normale** : les autres difficultés les font varier dans la même proportion (verrouillage, présence des renforts, détection) ou du même écart (nombre de vagues).

| Directive | Effet | Limites |
|---|---|---|
| `@lockdown 120` | secondes entre l'alerte et le verrouillage | 30 à 600 |
| `@waves 2` | vagues de renforts | 0 à 8 |
| `@detect 1.2` | multiplie la vitesse de détection des gardes (et des caméras) | 0,3 à 3 |
| `@stay 20` | secondes de présence d'un renfort | 5 à 120 |
| `@ambient 90,100,130` | lumière ambiante (RVB) à la place de celle du thème | 0 à 255 |
| `@objective nom` | objectif de la carte (obligatoire pour « voler un vaisseau », qui partage la console `C` avec « couper l'alimentation ») | `steal_plans`, `cut_power`, `free_prisoner`, `steal_ship`, `steal_uniform` |

Une directive indiquée deux fois ou hors limites fait échouer le chargement, avec le numéro de ligne. Les missions livrées s'en servent : l'entraînement a un verrouillage très tolérant (240 s), le Destroyer un verrouillage serré, plus de renforts, des gardes plus attentifs et une lumière plus sombre.

### Champs commutables et boutons

Après une ligne `---`, une instruction par ligne (les lignes vides et les commentaires `;` sont ignorés) :

```
field a closed          # closed = actif (bloquant) au départ ; open = inactif (traversable)
field b open
button 1 toggles a b    # chaque pression du bouton 1 inverse l'état de a ET de b
```

Un même champ peut répondre à plusieurs boutons, et un bouton commander plusieurs champs. Les erreurs sont écrites en français avec le numéro de ligne du fichier : lettre ou chiffre utilisé sans être déclaré, champ ou bouton déclaré mais absent de la carte, bouton qui référence un champ inexistant, état inconnu, nom invalide, doublon, bouton placé deux fois, champ qui n'est pas formé de lignes droites. Un champ sans bouton n'est qu'un avertissement (journal et `Tilemap.warnings`).

Itinéraire d'un garde, après la grille : `@patrol x,y -> x1,y1 x2,y2 ...` où `(x, y)` est la tuile du `G`.
Le garde rejoint les points en boucle (A* entre chaque) ; sans itinéraire, c'est une sentinelle.

Orientation d'un vaisseau (le nez) : `@ship x,y -> N|E|S|O` (nord par défaut). Terminaux et caméras : `@terminal` et `@camera` (voir « Terminaux, caméras et lumière »). Astuces : `@tip x,y -> nom [rayon]`.

Niveaux de badge : `@door x,y -> n` (0 = s'ouvre sans badge, défaut ; 1 à 3 = badge de ce niveau ou plus) et `@keycard x,y -> n` (défaut 1). Les portes et badges sont colorés par niveau (vert 1, ambre 2, rose 3).

## Terminaux, caméras et lumière

### Terminaux à menu

Utiliser un terminal (`E`) **met le jeu en pause** et ouvre un menu. **Un terminal ne sait rien faire par défaut** : sans directive, il ne propose que le téléchargement de données ; ses autres pouvoirs sont déclarés dans la carte :

```
@terminal x,y -> data lights cameras cells    (dans n'importe quel ordre)
@terminal x,y -> cameras:ab                   (seulement les caméras des groupes a et b)
```

| Pouvoir | Opération du menu | Effet |
|---|---|---|
| `data` | Télécharger les données | l'objectif « voler les plans » (le terminal de données est unique ; connexion de 2,5 s) |
| `cameras` | Désactiver les caméras | les caméras visées s'éteignent 40 s (connexion de 1,6 s) |
| `lights` | Couper la lumière de la salle | les lampes de **la salle du terminal** s'éteignent 25 s et les disjoncteurs font du bruit (connexion de 1,6 s) |
| `cells` | Ouvrir les cellules | **toutes** les portes de cellule `J` de la carte s'ouvrent d'un coup, avec beaucoup de bruit (connexion de 1,6 s) |

Choisir une opération ferme le menu et lance une **connexion** : il faut rester près du terminal (barre et étincelles sur l'écran) ; s'en éloigner la coupe (« Connexion perdue »). Le menu grise ce qui est déjà fait. Un terminal qui ne télécharge pas de données ne compte pas pour l'objectif.

### Caméras de surveillance

```
@camera x,y -> N|E|S|O [groupe] [amplitude]
```

`x,y` est la tuile de **mur** qui porte la caméra, la direction est celle où elle regarde, le groupe est une lettre (`a` par défaut) que les terminaux désignent, l'amplitude du balayage est en degrés de chaque côté (42 par défaut). Le cône **balaie** et se teinte de rouge à mesure que la caméra se méfie : elle repère le joueur comme un garde (plus vite de près, de jour ou en course, plus lentement accroupi ou dans l'ombre) mais **ne donne pas l'alerte générale** : elle envoie les gardes les plus proches vérifier sur place et reste sur le joueur 5 s. La pastille passe à « SUSPECT » dès qu'elle commence à le voir. Un terminal `cameras` les désactive 40 s. `check_level` vérifie qu'un terminal `cameras` a de quoi commander.

### L'éclairage influence la détection

La clarté à l'endroit du joueur (ambiance de la carte + lampes en vue, lanternes) multiplie la vitesse à laquelle gardes **et** caméras le repèrent : de ×0,5 dans le noir complet à ×1,25 en pleine lumière. Le HUD l'annonce sous la posture (« Visibilité : dans l'ombre / pénombre / en pleine lumière »). Les lampes qui grésillent créent des fenêtres, couper l'alimentation (console) ou la lumière d'une salle (terminal) en fait une cachette. L'effet existe même si l'éclairage dynamique est désactivé dans les réglages.

## Objets et interactions

| Objet | Rôle |
|---|---|
| Badge (niv. 1 à 3) | ouvre les portes de son niveau ou moins ; non consommé |
| Terminal | `E` ouvre un **menu** (le jeu est en pause) ; le choix lance une connexion pendant laquelle il faut **rester près du terminal** (voir « Terminaux, caméras et lumière ») |
| Données | objectif « voler les plans » : sans elles, la zone d'extraction refuse |
| Console de contrôle (`C`) | maintenir `E` ~3,5 s : **coupe l'alimentation** (les lampes s'éteignent, le disjoncteur fait du bruit) ; la zone d'extraction s'ouvre |
| Leurre | `F` le lance vers la souris (portée limitée, arrêté par les murs) ; il bipe 5 s et attire les gardes |

- Les objets au sol se ramassent en les touchant. L'inventaire s'affiche en bas à droite, l'objectif en haut.
- Ouvrir une porte fait un peu de bruit, et une porte ouverte le reste : les gardes peuvent la franchir.
- Mission : récupérer un badge, pirater le terminal, puis rejoindre la sortie (située dans la salle de départ) avec les données.

### Objectifs de mission

Chaque mission a **un objectif**, déclaré dans `assets/campaign.json` (`"objective"`) et porté par un point de la carte ; la zone d'extraction ne s'ouvre qu'une fois l'objectif accompli. `check_level` vérifie que le point existe, est unique et atteignable.

| Objectif | Point de la carte | Ce qu'il faut faire |
|---|---|---|
| `steal_plans` (défaut) | un terminal `T` qui sait télécharger des données | l'utiliser, choisir « Télécharger les données » et rester près de lui pour récupérer les données |
| `cut_power` | une console `C` | l'atteindre (salle de contrôle, souvent derrière un badge) et couper l'alimentation : les lampes s'éteignent, plus de gyrophares |
| `free_prisoner` | un prisonnier `Q` dans une cellule | ouvrir sa cellule (terminal « cellules », ou badge si la carte le demande), le **délivrer** (maintenir `E`, près de lui) puis **ressortir avec lui** : il suit à la marche, plus lentement que vous en courant, et la sortie reste fermée (« Attendez le prisonnier ») tant qu'il n'est pas tout près |
| `steal_ship` | une console `C` et un vaisseau contre la zone d'extraction (`@objective steal_ship`) | atteindre la salle de contrôle et **libérer les vaisseaux** (maintenir `E` 4 s) : les rayons tracteurs s'éteignent et les attaches s'ouvrent, puis rejoindre la passerelle du vaisseau marqué par une flèche verte pour **embarquer** |
| `steal_uniform` | un casier `U` | fouiller le casier d'un officier (maintenir `E` 2,2 s, un peu de bruit) : l'uniforme entre dans le sac, puis rejoindre la sortie |

Les missions « Coupure de courant », « Le poste radar d'Endor » et « Le Destroyer » utilisent `cut_power`, « Le vestiaire impérial » `steal_uniform`, « Le centre de détention » `free_prisoner` et « Vol de la navette » `steal_ship`. 
### Mode développeur

`python main.py --dev` (ou `STAR_INFILTRATION_DEV=1`) ajoute **Mode développeur** au menu principal : la liste de toutes les missions (sans les débloquer) et des cartes de `assets/maps` hors campagne, à lancer directement, plus deux interrupteurs persistants (*invincible*, *fantôme*). Ces parties n'ont pas de mission : ni score ni enregistrement, la progression n'est jamais touchée. En jeu, un bandeau « DEV » s'affiche et des raccourcis s'ajoutent à F3 (debug) et F4 (éclairage) : **F5** invincible, **F6** fantôme (gardes et caméras ne voient ni n'entendent), **F7** badges 1 à 3 et leurres, **F8** objectif accompli, **F9** aller à l'objectif, **F10** aller à la sortie. Le mode n'existe pas dans un exécutable empaqueté ni dans la version web (`dev.dev_allowed`).

### Acoustique

- **Occlusion filtrée.** Un son qui traverse des murs ou des portes fermées arrive *sourd* : filtre passe-bas (1 500 Hz pour un mur, 800 pour deux, 420 pour trois et plus, `settings.MUFFLE_CUTOFFS`) et 30 % de volume en moins par mur. Ouvrir la porte rend le son net. Concerne les sons localisés (portes, boutons, champs, leurre, vapeur, gardes).
- **Réverbération par salle.** Un son résonne selon la surface de la zone connexe où il retentit (`Tilemap.region_size`) : rien dans un réduit, un peu de résonance dans une salle (120 tuiles et plus), beaucoup dans un hangar (450 et plus). Vos pas résonnent dans votre propre salle.
- **Voix et radios.** Un garde lance une réplique quand il soupçonne, repère ou perd le joueur ; la radio crachote à l'alerte, à l'arrivée des renforts et quand une caméra vous repère. Les variantes se tirent dans un sac mélangé (aucune ne se répète avant que toutes soient passées), jamais deux voix en même temps (`VOICE_GAP`), et une catégorie ne se répète pas aussitôt (`VOICE_CATEGORY_COOLDOWN`). Les fichiers fournis sont synthétisés : à remplacer par des enregistrements du même nom.

Les variantes filtrées sont fabriquées au premier besoin (`core/dsp.py`) puis gardées en mémoire ; les ambiances en boucle ne sont pas filtrées (elles ont leur propre atténuation par les murs).

### Le déguisement

Un uniforme dérobé se porte avec `U` (LB à la manette). En uniforme :

- les gardes et les caméras **ne vous repèrent pas au-delà de 72 px** (un peu plus de deux tuiles) tant que vous **marchez** ; plus près, ils se méfient trois fois moins vite que d'habitude ;
- vos pas ne font plus de bruit ; en revanche **courir ou s'accroupir trahit** : la détection redevient celle de l'infiltration classique (sans bonus de discrétion) ;
- **l'alerte générale grille la couverture** (« Couverture grillée ») : l'uniforme ne trompe plus personne ;
- les **portes du personnel** (`@door x,y -> uniform`, voyant gris-vert) ne s'ouvrent qu'avec l'uniforme *porté* : aucun badge n'y fait rien.

Une mission peut donc **exiger** le déguisement : *Le quartier général* garde ses plans derrière une porte du personnel. `level_check.explore(carte, allow_uniform=False)` le prouve (le joueur parfait ne finit pas sans uniforme), et `check_level` refuse une carte qui a une porte du personnel mais aucun casier.

Pour ajouter un objectif : une entrée dans `game/objectives.py`, une entité interactive, une branche dans `PlayScene.objective_done`.

## Éclairage

La lumière ambiante est sombre ; le niveau est éclairé par :

- des **lampes de plafond** placées automatiquement (une par bloc de 8 tuiles, teinte propre à chaque salle), avec **ombres portées par les murs** : ouvrir une porte laisse passer la lumière. Environ une lampe sur huit grésille ;
- le **joueur** (halo), les **gardes** (halo + lampe torche qui épouse leur cône de vision, rouge quand ils poursuivent), les **terminaux**, la **sortie** (plus vive quand on a les données), les **portes** (couleur du badge), les **objets** au sol et les **leurres** (flash à chaque bip) ;
- pendant l'**alerte globale**, l'ambiance vire au rouge pulsant et les lampes deviennent des gyrophares.

F4 désactive l'éclairage (utile sur une machine lente). Réglages dans `game/settings.py` (section « Éclairage »).

## Alerte globale

Dès qu'un garde se met à vous poursuivre, **l'alerte est donnée** pour toute la partie :

- un chronomètre de **verrouillage** démarre (150 s) ; à zéro, le croiseur est scellé et la mission échoue. L'alerte ne se lève jamais : il faut fuir ;
- tous les gardes deviennent plus vigilants (détection ×1,5) et plus rapides en patrouille et en enquête (×1,25) ;
- tant qu'un garde vous voit, il le signale par radio toutes les 3 s : les 3 gardes les plus proches viennent enquêter sur votre dernière position ;
- des **renforts** arrivent aux points `R` de la carte : 3 vagues d'un garde (la première après 12 s, puis toutes les 35 s), 3 présents au maximum. Ils apparaissent hors de votre vue, à plus de 10 tuiles, et seulement là où ils peuvent vous atteindre. Ils fouillent votre dernière position connue puis gardent la sortie, et **se retirent après 25 s** (sauf en pleine poursuite). On les reconnaît à leur anneau bleu.

Le halo rouge sur les bords de l'écran et le chronomètre (qui clignote sous 20 s) signalent l'alerte.

## Champs de force commutables

Des portes énergétiques, distinctes des portes à badge, que l'on ouvre et ferme avec des **boutons** (E à moins d'une tuile, invite « Actionner »).

- **Actif = solide** (bloque le joueur et les gardes) ; **inactif = traversable**. Dans les deux cas on voit à travers.
- **Pas d'écrasement.** Si quelqu'un (joueur ou garde) est dans la zone au moment où le champ doit s'activer, il passe « en attente » (sa bande clignote) et ne se ferme que lorsque la zone est libre : personne n'est jamais coincé dedans.
- **Délai anti-répétition** de 0,4 s sur les boutons.
- **Lisibilité** : un bouton et ses champs partagent une teinte (cyan par défaut, puis ambre, magenta, vert, violet, corail ; les boutons qui se partagent un champ forment un seul groupe). Actif : bande d'énergie animée entre deux émetteurs allumés. Inactif : émetteurs éteints seulement. F3 trace un trait entre chaque bouton et ses champs, avec l'état de chacun (fermé, ouvert, attente).
- Événements : `button_pressed(button)` et `field_toggled(field, active)` (état voulu), pour que gardes et sons y réagissent plus tard.

Dans le croiseur : le hangar, l'ingénierie et le quai sont alignés par deux tunnels. Le champ `a` (hangar → ingénierie) est fermé et le champ `b` (ingénierie → quai) ouvert ; le bouton 1 (hangar) les inverse tous les deux, le bouton 2 (ingénierie) rouvre `b`. Le bouton 3, dans le poste de commandement, ouvre l'alcôve du terminal. L'entraînement a un bouton qui ouvre un raccourci et ferme un passage.

## Décor et obstacles

| Obstacle | Arrête le corps | Arrête la vue, la lumière, le bruit |
|---|---|---|
| Mur, porte fermée | oui | oui |
| Caisse, conteneur, vaisseau | oui | oui (ils projettent des ombres et servent d'abris) |
| **Champ de force** (permanent ou commutable actif) | oui | **non** : on voit et la lumière passe, mais on ne traverse pas |
| Vide de l'espace | oui | oui |

- Les baies d'amarrage (hangar de départ, quai d'extraction) ouvrent sur l'espace derrière un champ de force animé (pylônes, impulsions, lueur bleue) ; les vaisseaux sont garés devant, le nez vers le champ.
- Les caisses de la coursive coupent les lignes de vue ; les conteneurs de fret ont des couleurs variées.
- Les portes ont des vantaux qui coulissent dans les murs à l'ouverture (0,4 s, purement visuel : la porte est franchissable tout de suite), des montants, des chevrons de danger et un voyant d'état : rouge qui pulse (verrouillée), couleur du badge (prête), blanc (s'ouvre), vert (ouverte).

## Les gardes

| État | Comportement |
|---|---|
| Patrouille | suit son itinéraire, pause à chaque point |
| Enquête | va (A*) vers un bruit ou la dernière position connue du joueur |
| Fouille | balaie le regard sur place, puis reprend sa patrouille |
| Poursuite | fonce sur le joueur (A* si la voie n'est pas libre), l'abandonne après 1,5 s sans le voir |

- **Vue** : cône de 80° sur 7 tuiles, bloqué par les murs. La détection n'est pas instantanée : une jauge se remplit (bulle `?`), plus vite de près et quand on court, moins vite accroupi.
- **Ouïe** : marcher et courir émettent des pas audibles (le rayon s'affiche avec F3) ; accroupi ou immobile, on est silencieux. Chaque mur traversé étouffe le bruit.
- Un garde en poursuite qui touche le joueur le capture.

## Feuille de route

- [x] **Jalon 1** : squelette, boucle de jeu, joueur, carte en tuiles
- [x] **Jalon 2** : collisions, caméra
- [x] **Jalon 3** : gardes (patrouille, cône de vision, états Patrouille/Poursuite)
- [x] **Jalon 4** : pathfinding A*, perception du bruit, enquête
- [x] **Jalon 5** : interactions (badges, portes, terminaux, inventaire, leurres)
- [x] **Jalon 6** : alerte globale, renforts, fuite chronométrée
- [x] **Jalon 7** : niveau complet, sons, menus, équilibrage

## Pistes pour la suite

> **D'autres idées**, nouvelles et sans doublon avec cette liste (surfaces de sol, déguisement, carte de chaleur des détections, compagnon, replay, distribution...), sont dans [AMELIORATIONS.md](AMELIORATIONS.md).

Aucune n'est commencée. Cette liste sert à **choisir** : chaque idée a un identifiant (`A3`, `B2`...) pour qu'on puisse dire « je prends A1, A2 et C3 ». Elle tient compte du mode histoire prévu (plusieurs cartes, une progression).

**Effort** : **S** = une séance, **M** = quelques séances, **L** = gros chantier. La colonne « S'appuie sur » indique ce qui existe déjà dans le code.

### A. Mode histoire et progression

| ID | Idée | Ce que ça apporte | Effort | S'appuie sur |
|---|---|---|---|---|
| A1 | **[fait]** **Écran de fin de mission** : temps, alertes déclenchées, leurres utilisés, rang (« Fantôme » si aucune alerte, etc.) | Rejouabilité, fierté de bien jouer, enchaînement naturel vers la mission suivante | S | événements `mission_complete`, `alert_raised`, `Hud._draw_end_screen` |
| A2 | **[fait]** **Fichier de campagne** : liste ordonnée de missions avec titre, carte, briefing, difficulté conseillée | Ajouter une mission = ajouter une ligne, sans toucher au code | S | `assets/campaign.json`, `game/campaign.py` |
| A3 | **[fait]** **Sauvegarde de progression** : missions débloquées, meilleurs scores et rangs | Un vrai mode histoire qu'on reprend le lendemain | S | `Preferences` (JSON tolérant, dossier utilisateur) |
| A4 | **[fait]** **Carte de la campagne** : écran de sélection des missions (verrouillées, terminées, rang obtenu) | Sensation de progression | M | `MenuScene`, `Starfield` |
| A5 | **[en partie]** **Briefings et fin de mission racontés** (le générique défilant est fait ; restent les dialogues radio, portraits et texte de fin) : texte défilant façon « il y a longtemps... », portraits, dialogues radio | Donne un fil narratif et un ton | M | `MenuView`, `Starfield` |
| A6 | **[en partie]** **Objectifs multiples et secondaires** (voler des plans et couper l'alimentation sont faits ; la libération de prisonnier est préparée : tuile `Q`, objectif non jouable ; restent les objectifs secondaires) | Des missions variées au lieu d'« un terminal, une sortie » | M-L | `game/objectives.py`, `PlayScene.objective_done` |
| A7 | **Équipement choisi au briefing** (nombre de leurres, un gadget, un badge de départ) et qui évolue avec l'histoire | Progression du personnage sans arbre de compétences | M | `Inventory`, `Item` |
| A8 | **Points de reprise (checkpoints)** : après une capture, reprendre à la dernière salle franchie | Missions longues moins frustrantes | M | `restart()`, état des champs, des portes, de l'inventaire |
| A9 | **Récits dans le niveau** : holo-journaux et terminaux à lire, qui racontent l'histoire en explorant | Récompense l'exploration, étoffe l'univers sans cinématique | M | `Terminal`, `Pickup` |
| A10 | **Nouvelle partie +** : mêmes missions, gardes plus attentifs, objets déplacés | Prolonge la durée de vie à peu de frais | S | `Difficulty`, `Guard.sensitivity` |

### B. Furtivité et gameplay

| ID | Idée | Ce que ça apporte | Effort | S'appuie sur |
|---|---|---|---|---|
| B1 | **[fait]** **Caméras de sécurité** : cône qui balaie, désactivables depuis un terminal ou un bouton | Un danger fixe qui complète les patrouilles, et une raison d'utiliser les terminaux | M | `vision_points`, `can_see`, `AlertSystem`, `FieldButton` |
| B2 | **Neutraliser un garde** par derrière, puis cacher le corps (un corps découvert déclenche l'enquête) | Une façon active de jouer, au-delà de se cacher | M-L | états de `Guard`, `hear`/`alarm` |
| B3 | **Cachettes** (casiers, conduits) où le joueur disparaît de la vue | Plus d'options quand un garde approche | M | `Interactable`, `Prompt` |
| B4 | **Les gardes réagissent aux portes, boutons et champs** : porte ouverte laissée derrière soi, champ qui change d'état | Le monde réagit à ce que fait le joueur ; les événements existent déjà | S | `door_opened`, `button_pressed`, `field_toggled` (émis, personne n'y réagit encore) |
| B5 | **[fait]** **L'éclairage influence la détection** : dans l'ombre on est moins visible, une lampe qui grésille crée une fenêtre | Donne un vrai rôle gameplay à l'éclairage | M | `Lighting`, `Player.detectability`, `flicker_factor` |
| B6 | **[fait]** **Couper la lumière depuis un terminal** (une salle devient sombre) | Un nouvel usage des terminaux, très lisible | M | `Lighting`, `Terminal.interact` |
| B7 | **Retour au calme** : l'alerte retombe si on reste invisible un moment (aujourd'hui elle ne se lève jamais) | Moins punitif, davantage de tension montante/descendante | S-M | `AlertSystem.update` |
| B8 | **Niveaux de suspicion plus fins** (curieux, recherche active, alerte générale) avec des réactions différentes | Des gardes plus crédibles | M | `GuardState`, `awareness` |
| B9 | **Gardes qui ouvrent les portes** et utilisent les badges, poursuite à travers plusieurs salles | Poursuites moins prévisibles | M | `plan_route`, `Tilemap.open_door` |
| B10 | **Types d'ennemis** : sentinelle fixe, droïde sourd mais à large vision, officier qui porte un badge à voler | Variété sans nouvelle mécanique de base | M | `Guard` (paramètres de vue, d'ouïe, de vitesse) |
| B11 | **Gadgets** : brouilleur (désactive caméras et champs un instant), fumigène, grappin | Plus de façons de résoudre un problème | M chacun | `Inventory`, `Decoy` comme modèle d'objet utilisable |
| B12 | **Mini-jeu de piratage** (mémoire, rythme) à la place du maintien de E | Plus d'engagement, difficulté réglable par terminal | M | `Terminal.hold_time`, `Hud` |
| B13 | **Combat léger** (tir, santé) pour les passages « on est découvert » | Ouvre d'autres styles de jeu, mais change l'esprit du jeu : à décider avec soin | L | `Guard.can_catch` (aujourd'hui capture immédiate) |
| B14 | **Recherche par zone** : les gardes fouillent méthodiquement la zone où ils ont perdu le joueur | IA plus crédible, fuites plus intéressantes | M | `GuardState.SEARCH`, `pathfinding` |

### C. Immersion (image, son, ambiance)

| ID | Idée | Ce que ça apporte | Effort | S'appuie sur |
|---|---|---|---|---|
| C1 | **Vrais sprites animés** (marche, accroupi, garde, ouverture) à la place des formes dessinées | Le gain visuel le plus fort | L | `Entity.draw`, `assets/sprites/` |
| C2 | **Répliques des gardes** en bulles de texte (« Tu as entendu ? », « Alerte ! ») | Donne vie aux gardes, très peu coûteux | S | `SoundDirector` (déjà abonné aux états des gardes), `WorldOverlay` |
| C3 | **Ambiances sonores par salle** (ronronnement des moteurs au hangar, silence dans les quartiers) et musique propre à chaque mission | Chaque lieu a sa personnalité | M | `Audio` (couches de musique), `place_ceiling_lamps` pour les zones |
| C4 | **Effets visuels** : étincelles de piratage, poussière sous les pas, tremblement à l'alerte, éclats de porte | Retours plus vivants | M | `Player.made_step`, événements |
| C5 | **Transitions** (fondus entre menus, niveaux et pause) et petite animation d'ouverture de mission | Finition qui change la perception de qualité | S | `SceneManager` |
| C6 | **[fait]** **Thèmes visuels par mission** : palette, murs et sols différents (hangar, mines, cité) via une directive `@theme` | Les niveaux ne se ressemblent plus | M | `COLORS`, `Tilemap.draw`, `Lighting` |
| C7 | **Décor vivant** : écrans qui clignotent, vapeur, vaisseaux qui passent derrière les champs de force | L'espace n'est plus figé | S-M | `SpaceLayer`, `prop_art` |
| C8 | **Brouillard de guerre** : on ne voit que ce qu'on a exploré ; les zones quittées s'assombrissent | Tension d'exploration, très bon avec la lumière | M-L | `Lighting`, `line_of_sight` |
| C9 | **[fait]** **Caméra plus expressive** : légère avance dans le sens du déplacement, zoom en pause ou en poursuite | Meilleure lisibilité et dynamisme | S | `Camera.update` |

### D. Confort et expérience joueur

| ID | Idée | Ce que ça apporte | Effort | S'appuie sur |
|---|---|---|---|---|
| D1 | **Astuces contextuelles** dans l'entraînement (« Maintenez E pour pirater ») via une directive `@hint x,y -> texte` | L'entraînement explique sans texte à lire en dehors du jeu | S-M | `Hud.notify`, directives de carte |
| D2 | **[fait]** **Remappage des touches** dans les Réglages (QWERTY/AZERTY, au choix du joueur) | Les touches ne sont modifiables aujourd'hui qu'en éditant `settings.py` | M | `KEYS`, `Preferences`, `SettingsScene` |
| D3 | **[fait]** **Manette** (déplacement analogique, boutons d'action) | Jouable sans clavier | M | `InputState`, `read_input` |
| D4 | **Mini-carte** (et carte plein écran) avec objectifs et salles découvertes | On ne se perd plus dans de grandes cartes | M | `Tilemap`, `explore` pour les zones |
| D5 | **Accessibilité** : daltonisme (formes ou symboles en plus des teintes des champs et boutons), réduction des clignotements, taille du texte | Jeu ouvert à plus de joueurs ; les teintes `link_N` ne sont pas lisibles pour tous | M | `COLORS`, `prop_art`, `Hud` |
| D6 | **Indicateur de bruit optionnel** (onde autour du joueur), désactivé par défaut | Retiré à ta demande du rendu normal ; proposé seulement comme aide | S | événement `noise` |
| D7 | **Succès et statistiques** (« Fantôme », « Sans leurre », temps, parties) | Objectifs de rejouabilité | S-M | `Preferences`, événements |
| D8 | **Difficulté personnalisée** (cône plus court, chronomètre désactivé, mode « sans capture ») | Chacun règle son niveau de défi | S | `Difficulty` |
| D9 | **Contrôles et journal de mission dans la pause** (rappel des touches, objectif détaillé) | Moins de retours au README | S | `PauseScene` |
| D10 | **Langues** : textes dans des fichiers (français, anglais) | Les chaînes sont aujourd'hui dans le code | M | tout le texte affiché |
| D11 | **Options graphiques** (résolution, qualité de l'éclairage, limite de FPS) | Joue bien sur des machines modestes | S-M | `LIGHT_DOWNSCALE`, `Game` |

### E. Outils et solidité technique

| ID | Idée | Ce que ça apporte | Effort | S'appuie sur |
|---|---|---|---|---|
| E1 | **[fait]** **Réglages par carte** (`@lockdown 120`, `@waves 2`, `@ambient ...`) | Chaque mission a son équilibrage sans toucher au code | S-M | directives de `Tilemap`, `Difficulty` |
| E2 | **Mode debug étendu** : téléportation, invincibilité, chronomètre figé, affichage des états des gardes | Tester vite une mission à la fin de la campagne | S-M | `PlayScene.debug` |
| E3 | **Vérifier toutes les cartes en ligne de commande** et automatiquement (`pytest` à chaque modification, intégration continue) | Une carte cassée est détectée tout de suite | S | `check_level`, `explore` |
| E4 | **Journal des plantages** : une exception est écrite dans un fichier et affichée proprement | Les erreurs en jeu ne disparaissent plus avec la fenêtre | S | `Game.run` |
| E5 | **Éditeur de cartes** ou import depuis Tiled | Créer les cartes de la campagne bien plus vite | L (Tiled : M) | `Tilemap.from_text` ; le docstring prévoit déjà un chargeur Tiled |
| E6 | **[fait]** **Empaquetage** (exécutable Windows/macOS/Linux, version web) | Faire jouer d'autres personnes sans installer Python | M | `main.py` |
| E7 | **Optimisation de l'éclairage** (aujourd'hui 3 ms par image sur 10 à 13 ms) | Marge sur les machines lentes | M | `Lighting` |

### F. Idées de missions pour la campagne

Pour une campagne variée, chaque mission peut mettre une mécanique en avant. Les pistes ci-dessous disent ce qu'elles demanderaient :

| Mission | Principe | Demande |
|---|---|---|
| **Évasion** | On commence désarmé dans une cellule, sans équipement, et on récupère le matériel en route | A6, A7 |
| **Zéro alerte** | Une seule alerte et la mission échoue | A1 (compteur d'alertes) |
| **Sabotage** | Poser des charges en trois points puis fuir avant le compte à rebours | A6, B12 |
| **Infiltration de nuit** | Salles plongées dans le noir, on coupe les lumières pour passer | B5, B6 |
| **Cible mobile** | Un officier se déplace ; il faut le suivre sans être vu | B8, B10 |
| **Fuite finale** | Pas de furtivité : traverser le croiseur en poursuite avec un chronomètre court et des renforts | B7, A8 |
| **Vol de navette** | Atteindre la baie, déverrouiller le vaisseau garé, puis séquence de départ | C1, C7 |

### Choix à faire pour le mode histoire

Avant de décider du reste, quelques questions orientent beaucoup de choix :

1. **Campagne linéaire ou à choix ?** Aujourd'hui une mission se débloque en terminant la précédente (linéaire). Une campagne à embranchements demanderait de remplacer cette règle dans `Campaign.is_unlocked`.
2. **Le joueur garde-t-il son équipement d'une mission à l'autre ?** Oui : A7 devient central. Non : on peut s'en passer.
3. **Après une capture, on recommence la mission ou on reprend à un point de reprise ?** Cela décide de A8 et pèse sur la longueur des cartes.
4. **Combat ou pas ?** B13 change l'esprit du jeu : mieux vaut l'écarter ou l'assumer dès le début.
5. **Quelle part de narration ?** Textes seuls (A5, A9), ou voix et cinématiques ?

### Combinaisons suggérées

- **Socle de campagne** : A2, A3, A1 sont faits ; restent E1 et D1 pour enchaîner confortablement plusieurs cartes.
- **Furtivité plus riche** : B4, B7, B5, B1, B2. Les gardes et le monde réagissent davantage.
- **Immersion rapide** : C2, C5, C9, C4. Peu coûteuses, effet immédiat.
- **Confort** : D2, D5, D9, D6. Pour un jeu agréable à reprendre.
- **Pour aller plus loin visuellement** : C1, C6, C8. Les plus lourdes, mais les plus visibles.

À noter avant d'ajouter beaucoup de cartes : un seul objectif par mission pour l'instant (voir A6). La liste des niveaux est dans `assets/campaign.json`.
