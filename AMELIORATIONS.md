# Autres améliorations possibles

Ce fichier **complète** la feuille de route du [README](README.md#pistes-pour-la-suite) (identifiants `A1` à `E7`) : il ne reprend aucune de ses idées, faites ou non, ni rien de ce qui existe déjà dans le jeu. Ce sont des pistes **nouvelles**, à choisir comme les autres : chacune a un identifiant (`G1`, `H3`...) pour qu'on puisse dire « je prends G2, H1 et K4 ».

**Effort** : **S** = une séance, **M** = quelques séances, **L** = gros chantier. La colonne « S'appuie sur » indique ce qui existe déjà dans le code. Seul H1 est fait ; le reste n'est pas commencé.

## Ma sélection

Les huit idées qui changeraient le plus l'expérience pour le moins de travail, dans l'ordre où je les prendrais :

1. **G1 Surfaces de sol** : le bruit dépend du sol, donc le trajet compte autant que la posture. Petit chantier, gros effet sur les décisions du joueur.
2. **J1 Carte de chaleur des détections** à l'écran de résultats : on voit enfin *où* on s'est fait repérer, et on a envie de recommencer.
3. **G5 Pouvoirs de terminal supplémentaires** (portes à distance, fausse alerte) : la mécanique de menu existe déjà, chaque pouvoir est un ajout isolé.
4. **I1 Escorte plus vivante** : le prisonnier suit déjà le joueur, mais il ne risque rien ; lui donner des ennuis rend l'évasion bien plus tendue.
5. ~~**H1 Déguisement**~~ **[fait]** : uniforme à dérober, touche `U`, portes du personnel, missions « Le vestiaire impérial » et « Le quartier général ».
6. **K1 Séquence de fuite en vol** après le vol de navette : donne enfin un vrai dénouement à cette mission.
7. **L4 Version web complète** (sons en OGG dans la CI) : c'est le seul empaquetage resté inachevé.
8. **L1 Replay déterministe** : il rend tous les bogues de gameplay reproductibles, et ouvre la porte au fantôme du meilleur temps (J2).

---

## G. Furtivité et systèmes de jeu

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| G1 | **Surfaces de sol** : grilles métalliques bruyantes, tapis qui étouffent les pas, flaques qui éclaboussent, sable qui absorbe | Le choix du trajet devient tactique, et chaque thème a ses propres sons de pas | S-M | `Player.noise_radius`, `PLAYER_NOISE`, `tile_art` |
| G2 | **Endurance de course** : une jauge qui se vide en courant et se recharge en marchant | Courir devient un choix, plus un réflexe permanent | S | `Player.stance`, `Hud` |
| G3 | **Lampe torche du joueur** : éclaire plus loin mais se voit de loin, batterie limitée | Un arbitrage direct entre voir et être vu, lié à l'éclairage déjà mesuré | S-M | `PLAYER_LIGHT`, `light_factor`, `exposure.light_at` |
| G4 | **Portes verrouillables ou à forcer** : crocheter une porte (long, bruyant) quand on n'a pas le badge | Une alternative risquée au badge, sans nouvelle carte | M | `Door`, `InteractionSystem`, `DOOR_NOISE` |
| G5 | **Pouvoirs de terminal supplémentaires** : verrouiller ou ouvrir des portes à distance, déclencher une fausse alerte loin du joueur, couper une tourelle, appeler un ascenseur | Les terminaux deviennent la boîte à outils du niveau ; chaque pouvoir est un ajout isolé | S chacun | `terminals.py`, `PlayScene._update_terminals` |
| G6 | **Dangers de décor** : grilles laser, tourelles à cône fixe, sols électrifiés, vapeur brûlante | Des obstacles qui ne sont pas des gardes, et qu'un terminal ou un bouton peut couper | M | `SecurityCamera` (même cône), `FieldButton` |
| G7 | **Ronde qui change** : relève des gardes à heure fixe, itinéraires différents selon que l'alerte est donnée ou non | Les patrouilles se lisent mieux, et apprendre leur rythme est récompensé | M | `Guard.route`, `@patrol` |
| G8 | **Escalade des caméras** : au troisième repérage, la caméra donne l'alerte générale (aujourd'hui elle envoie seulement deux gardes) | Donne un vrai enjeu à une caméra qu'on laisse voir | S | `camera_spotted`, `AlertSystem` |
| G9 | **Mouvements de joueur supplémentaires** : se plaquer contre un mur, ramper sous un obstacle bas, sauter par-dessus une caisse | Plus de manières de traverser une salle, sans changer les cartes | M | `Player`, `collision.move_and_collide` |

## H. Objectifs et missions

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| H1 | **[fait]** **Déguisement** : un uniforme volé permet de passer à distance des gardes, jusqu'à ce qu'on s'approche ou qu'on coure | Un style de jeu entier (l'ingénierie sociale), très « Star Wars » | M | `Player.detectability`, `Guard._update_awareness` |
| H2 | **Plusieurs objectifs par mission**, obligatoires ou facultatifs (voler les plans *et* libérer un prisonnier) | Des missions plus riches sans multiplier les cartes ; le score peut récompenser le facultatif | M | `objectives.py`, `PlayScene.objective_done` |
| H3 | **Objectif de sabotage** : poser des charges en plusieurs points puis fuir avant le compte à rebours | Reprend le décor déjà prévu (champs, consoles) avec une tension nouvelle | M | `PowerConsole`, `AlertSystem` |
| H4 | **Escorte d'un VIP ou d'un blessé** : plus lent, doit rester hors de vue, déclenche l'alerte s'il est vu | Prolonge le prisonnier vers une vraie mission d'escorte | M | `Prisoner`, `plan_route` |
| H5 | **Missions sans objet à voler** : atteindre un point à temps, ou tenir une position jusqu'à l'arrivée des renforts alliés | Variété de rythme dans la campagne | S-M | `ExitPad`, `AlertSystem` |
| H6 | **Étages multiples** : ascenseurs et escaliers qui relient plusieurs cartes d'une même mission | Des lieux plus grands et plus lisibles qu'une seule carte géante | L | `Tilemap`, `PlayScene._start_level` |

## I. Le prisonnier, un compagnon

Le prisonnier suit le joueur, mais il ne court aucun risque et ne sert à rien : voici de quoi en faire un vrai personnage.

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| I1 | **Escorte vivante** : les gardes peuvent le repérer et le reprendre, il peut paniquer et courir si l'alerte est donnée | Libérer quelqu'un devient une responsabilité, pas un simple déplacement | M | `Prisoner`, `Guard.update(target)` |
| I2 | **Compétences du prisonnier** : un pirate qui ouvre une porte, un pilote qui sait voler le vaisseau | Une raison de l'avoir libéré avant la sortie, et un lien avec le vol de vaisseau | M | `Prisoner`, `InteractionSystem` |
| I3 | **Ordres simples** : « reste ici », « suis-moi » | Cacher le compagnon pendant qu'on explore | S | `Prisoner._follow`, touches du jeu |

## J. Rejouabilité et fin de mission

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| J1 | **Carte de chaleur des détections** : l'écran de résultats montre où chaque garde ou caméra a repéré le joueur, et le trajet suivi | On comprend ses erreurs et on veut recommencer | M | `ResultsScene`, `Guard.awareness`, `mission_time` |
| J2 | **Fantôme du meilleur temps** : le trajet du meilleur essai rejoué en transparence | Un adversaire permanent contre soi-même, très motivant pour viser le rang S | M | `Progress`, `Player.pos`, dépend de L1 |
| J3 | **Missions générées** : une graine produit une carte et ses patrouilles | Une durée de vie quasi infinie, et un « défi du jour » partageable | L | `levelkit` (outil hors projet), `check_level` |
| J4 | **Classement local et partage de graine** : meilleurs scores par mission, avec le détail des rangs | Se comparer à soi-même et à ses amis sans serveur | S-M | `Progress`, `compute_result` |
| J5 | **Modificateurs de mission** à choisir avant de lancer : sans leurre, sans courir, chronomètre réduit, « un seul garde vous repère » | Des défis librement combinables, pour un coût très faible | S-M | `compute_result`, `MissionStats` |

## K. Immersion et ambiance

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| K1 | **Séquence de fuite en vol** après le vol de la navette : un court passage en vue de dessus, dans l'espace | Un vrai dénouement à « voler un vaisseau », au lieu d'un simple écran de résultats | L | `SpaceLayer`, `Starfield`, nouvelle scène |
| K2 | **Météo par thème** : tempête de sable à Tatooine (la vue des gardes baisse), brume à Endor | Une raison de choisir le moment de passer, et un décor qui joue | M | `Effects`, `GUARD_VISION_RANGE`, thèmes |
| K3 | **[fait]** **Occlusion sonore filtrée** : un son derrière un mur est sourd, pas seulement plus faible | Beaucoup plus d'impression d'espace | M | `Audio.play_at`, `ambience.mix` |
| K4 | **[fait]** **Réverbération par salle** (un hangar résonne, un bureau non) | Chaque lieu s'entend | M | `Audio`, taille de la zone (`Tilemap.region_of`) |
| K5 | **[fait]** **Voix et radios des gardes** : quelques répliques enregistrées par état, espacées pour ne pas répéter | Donne de l'âme aux gardes (en complément des bulles de texte déjà prévues) | M | `SoundDirector`, `Guard.state` |
| K6 | **Retour de manette** : vibration au pas lourd, à l'alerte, à la capture | Le jeu se sent, sans une ligne de graphisme | S | `gamepad.py` |

## L. Technique, outils et qualité

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| L1 | **Replay déterministe** : enregistrer la graine et les entrées, rejouer une partie à l'identique | Reproduire tout bogue de gameplay, et base du fantôme (J2) | M | `InputState`, `EventBus`, `MAX_DT` |
| L2 | **Captures de référence** : comparer le rendu de chaque carte et de chaque sprite à une image attendue | Un changement visuel imprévu (comme l'ombre rectangulaire d'un vaisseau) est détecté tout de suite | M | `tests/`, `PlayScene._draw_world` |
| L3 | **[fait]** **Lint en intégration continue** (ruff fait ; mypy reste à ajouter) | Le code reste propre à mesure qu'il grossit | S | `.github/workflows/build.yml` |
| L4 | **[fait]** **Version web complète** : installer `ffmpeg` dans le travail web de la CI (sons en OGG), vérifier le rendu dans un navigateur, ajouter des commandes tactiles | C'est le seul empaquetage resté sans vérification de bout en bout | M | `packaging/build.py`, `Audio._sound` |
| L5 | **Versions des fichiers de sauvegarde** : numéro de format dans `progress.json` et `preferences.json`, avec migration | Les prochaines évolutions ne casseront pas la progression d'un joueur | S | `Progress.load`, `Preferences.load` |
| L6 | **Documentation des directives générée** à partir du code | Le README ne peut plus être en retard sur `@theme`, `@camera`, `@terminal`... | S-M | les analyseurs de `Tilemap` |
| L7 | **Constantes de réglage en JSON** (vitesses, bruits, durées) | Équilibrer sans toucher au code, et ouvre la porte aux mods | M | `settings.py` |
| L8 | **Campagnes personnalisées** : un dossier de l'utilisateur contenant sa propre `campaign.json` et ses cartes | Les joueurs créent des missions sans toucher au jeu | M | `load_campaign`, `Mission.map_path` |
| L9 | **Télémétrie locale d'équilibrage** : compter où on est repéré, combien de temps dure chaque mission, combien de tentatives | Régler la difficulté sur des chiffres, pas sur des impressions | S-M | événements de l'`EventBus` |

## M. Confort et accessibilité

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| M1 | **Indicateurs hors écran** : une flèche au bord de l'écran vers un garde qui poursuit ou un bruit proche | On sait d'où vient le danger, sans changer le zoom de la caméra | S-M | `WorldOverlay`, `Camera.world_to_screen` |
| M2 | **Sous-titres sonores** : une icône à l'écran pour les bruits importants (alarme, pas lourds, porte) | Jouable en sourdine ou par un joueur sourd | S | `SoundDirector`, `Hud` |
| M3 | **Maintien ou bascule** : choisir si courir et s'accroupir se maintiennent ou s'activent d'un appui | Moins de fatigue pour les longues parties | S | `InputState`, `bindings` |
| M4 | **Profils de joueur** : plusieurs sauvegardes sur la même machine | Chacun garde sa progression | S-M | `Progress`, `Preferences` |
| M5 | **Zones de sécurité du texte et mise à l'échelle de l'interface** | Lisible sur un très grand ou un très petit écran | S-M | `Hud`, `MenuView` |

## N. Distribution (suite de l'empaquetage)

| # | Idée | Intérêt | Effort | S'appuie sur |
|---|---|---|---|---|
| N1 | **[fait]** **Icône et métadonnées** de l'application (Windows, macOS, Linux) | Un jeu qui a l'air d'un vrai jeu dans le dossier et la barre des tâches | S | `packaging/star_infiltration.spec` |
| N2 | **[fait]** **Signature et notarisation** (macOS), signature (Windows) | Plus d'avertissement de sécurité au premier lancement | M | workflow CI |
| N3 | **[fait]** **Installateurs** : `.dmg`, `.msi`/`.exe`, `.AppImage` | Une installation en un geste | M | `packaging/build.py` |
| N4 | **Publication sur itch.io** depuis la CI (via `butler`) | Des joueurs sans passer par GitHub | S | `.github/workflows/build.yml` |
| N5 | **Vérification de mise à jour** : le jeu signale qu'une nouvelle version existe | Les testeurs jouent toujours la dernière | S-M | `VERSION`, `main.py` |

---

## Questions à trancher

1. **Le jeu doit-il rester purement furtif ?** Les dangers de décor (G6) et un éventuel combat léger (B13 du README) ne vont pas dans le même sens que la discrétion pure ; il vaut mieux décider avant d'en prendre un.
2. **Une carte ou plusieurs étages ?** H6 change la façon de dessiner les niveaux ; s'il est un jour retenu, mieux vaut le décider avant d'ajouter beaucoup de cartes.
3. **Missions fixes ou générées ?** J3 demande de transformer l'outil de dessin des cartes (hors du projet) en vraie bibliothèque testée.
4. **Quelle plateforme viser d'abord ?** Elle commande la suite : un joueur sur navigateur a besoin de L4 et de commandes tactiles, un joueur sur bureau de N1 à N3.
