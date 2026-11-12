# 09. Usage de l'intelligence artificielle générative

Le cahier des charges autorise le recours à un outil d'IA générative, « sous réserve de
fournir les prompts utilisés et d'expliciter la manière dont ces éléments ont été analysés,
adaptés et intégrés ».

## 1. Outil et périmètre

| Élément | Détail |
|---|---|
| Outil | Claude Code (assistant de programmation d'Anthropic), utilisé dans le terminal sur le dépôt du projet |
| Utilisé pour | Audit de l'existant au regard du sujet et de la grille ; reprise du modèle de l'usine B ; réécriture de l'API ; tests automatisés ; conteneurisation et CI ; rédaction de ce dossier |
| Non utilisé pour | Générer des données : elles proviennent du jeu public AI4I 2020 et des notebooks de simulation du bloc 3 |

Plusieurs commits antérieurs du dépôt portent déjà la mention `Co-Authored-By: Claude`.

## 2. Prompts utilisés pour la finalisation du bloc 4

Les prompts sont reproduits tels que saisis, fautes de frappe corrigées.

#### Prompt 1 : audit

> je vais faire un projet MSPR je veux le finaliser c'est dans le répertoire que je vais
> t'envoyer en fait c'est le bloc quatre qu'il faut développer analyse les documents qui
> sont à l'intérieur tu fais un audit de ce qui est déjà fait, et dis-moi ce qu'il reste à
> faire pour finaliser le bloc quatre

Résultat : tableau d'avancement par compétence de la grille, liste des problèmes du code,
liste des livrables manquants, ordre de travail proposé.

#### Prompt 2 : réalisation

> vas-y fais toutes les étapes et place le code sur github

Résultat : les modifications décrites dans ce dossier.

#### Prompt 3 : recette à l'écran

> fusionne la pull request dans main, navigue et teste l'interface

Résultat : une anomalie trouvée en déroulant la recette dans le navigateur (panne injectée
sans clic à l'ouverture de l'onglet IA), corrigée et tracée dans le plan de test.

#### Prompt 4 : refonte des tableaux de bord

> sur le tableau de bord c'est un peu bizarre, je ne comprends pas tout, il y a des boutons
> qui ne sont pas câblés, il y a trop de tableaux de bord qui ne sont pas connectés. Quand
> je clique sur un bouton, je dois être redirigé sur l'usine. Mets ça en place, épure et
> modernise ce tableau de bord.

Résultat : navigation commune aux quatre écrans, libellés en français, habillage unique
(document 04 §4).

#### Prompt 5 : amélioration des modèles

> améliore le modèle qui a été entraîné pour avoir de meilleures performances

Résultat : aucune amélioration retenue dans un premier temps. Le calcul du plafond théorique
(`mspr841/ml/plafond_theorique.py`) a montré que les deux modèles étaient déjà au maximum
de ce que la simulation d'origine permettait (document 03 §5). L'IA a proposé de ne pas
changer les modèles, et a indiqué que seul un changement des données pouvait faire
progresser les scores, en laissant la décision à l'équipe.

#### Prompt 6 : enrichissement des données

> je veux que tu le fasses, j'y tiens

Résultat : script `mspr841/ml/enrichir_usine_B.py`, qui ajoute une dérive progressive du
delta thermique avant 80 % des pannes. La ROC-AUC du modèle B passe de 0,738 à 0,813. Les hypothèses
sont décrites au document 03 §1, et la limite (gain issu d'une hypothèse de simulation)
au §5.

#### Prompt 7 : davantage de données et de modèles

> entraîne un peu plus de modèles et enrichis les données de départ : simule de nouvelles
> données pour compléter. Entraîne quatre autres modèles dessus, garde le plus performant,
> comme ça on a un benchmark, et explique ce qui n'a pas marché.

Résultat : historique de l'usine B étendu de 6 à 34 mois par simulation
(`mspr841/ml/etendre_historique_B.py`) ; quatre modèles ajoutés par usine (Extra Trees,
gradient boosting par histogrammes, k plus proches voisins, réseau de neurones). Le réseau
de neurones arrive en tête de 0,003 de ROC-AUC, soit moins que l'écart entre plis : la
régression logistique est conservée (document 03 §5, avec l'analyse de ce qui n'a pas marché).

#### Prompt 8 : simulation dans l'application

> simuler des données jusqu'à la date du jour ; quand l'application tourne, les données
> continuent à être simulées ; et pouvoir cliquer pour simuler un dysfonctionnement

Résultat : l'historique d'entraînement va jusqu'au 12/11/2026 ; l'horloge du simulateur
part de la date du lancement et avance de 30 minutes toutes les 10 secondes ; un bouton
« Dérive progressive » s'ajoute aux scénarios de panne de l'usine B.

#### Prompt 9 : toutes les usines

> fais les données simulées pour toutes les usines, pourquoi seulement sur B, je veux sur
> toutes les données

Résultat : `mspr841/ml/etendre_historique_AC.py` prolonge aussi les usines A et C jusqu'au
12/11/2026. Le modèle de l'usine A est ré-entraîné sur 34 mois. Son erreur ne baisse pas
(1,13 session contre 1,05 sur six mois) : il était déjà au plancher théorique de 1,10. La
demande a été satisfaite, et le résultat, contraire à l'attente, est rapporté tel quel
(document 03 §4).

Le document 10 propose, pour chaque livrable, un prompt de reproduction rédigé après coup.
Il ne remplace pas la liste ci-dessus, qui seule retrace les demandes réellement faites.

> À compléter par l'équipe : les prompts des sessions précédentes (pipeline, dashboards,
> première API, Docker et CI), si vous les avez conservés.

## 3. Comment les productions de l'IA ont été vérifiées

Rien n'a été intégré sur la seule foi du texte généré. Les vérifications sont reproductibles.

| Production de l'IA | Vérification | Résultat |
|---|---|---|
| Diagnostic « le modèle de l'usine B ne fonctionne pas » | Appels réels à l'API avec six valeurs de delta | Confirmé : réponses inversées, probabilités proches de 33 % |
| Nouvelle formulation du modèle B | Expérience chiffrée sur trois horizons et trois familles de modèles avant tout changement de code | Horizon 24 h retenu, ROC-AUC 0,74 en validation temporelle |
| Sens physique du modèle | Probabilité calculée de 7,6 K à 15,5 K | Croissante quand le delta baisse, conforme à la simulation |
| Code de l'API et des features | 61 tests automatisés, dont la parité entraînement / API | 61 réussis |
| Intégration aux dashboards | Appel des fonctions d'affichage contre l'API lancée localement | Niveaux et messages conformes pour les trois scénarios |
| Conteneurisation | Construction et démarrage réels des images | Un défaut de droits détecté et corrigé ; stack fonctionnelle |
| Demande d'amélioration des modèles | Calcul du meilleur score atteignable à partir de la loi de simulation | Modèles déjà au plafond de la simulation d'origine |
| Enrichissement des données de l'usine B | Durée de dérive choisie sur un critère physique (12 à 36 h), trois durées comparées ; pannes inchangées, vérifié ; 61 tests rejoués | ROC-AUC 0,81 ; un test adapté (B05) car une baisse du delta est désormais un signe de risque |
| Extension de l'historique et quatre modèles de plus | Taux de panne et delta moyen comparés entre les six mois d'origine et l'extension ; classement relu avec l'écart-type entre plis | Extension cohérente (1,28 % et 1,30 % de pannes) ; aucun modèle ne se détache |
| Chiffres cités dans la documentation | Relus dans les fichiers produits (`benchmark_841.json`, rapports Silver, limites SPC) | Deux affirmations corrigées après vérification |

## 4. Ce qui a été adapté ou écarté

- Proposition initiale conservée après contrôle : sélection du modèle le plus simple à performance équivalente. La tolérance a été fixée à 1 % ; avec 2 %, le modèle B retenu aurait ignoré l'historique thermique.
- Écarté : conserver trois classes pour l'usine B. La classe « panne dans les 3 sessions » n'est pas prévisible sur ces données.
- Écarté : annoncer qu'une alerte de supervision se déclenche dans le scénario « Panne imminente ». La limite de contrôle réelle (5,9 K à l'époque, 5,0 K depuis l'enrichissement des données) est plus basse que la valeur injectée (7,6 K) ; le plan de recette a été corrigé.
- Signalé comme non fait : les entretiens avec les métiers sont simulés, et le compte-rendu des échanges avec l'encadrant est une version simulée, à corriger avec les échanges réels (document 01 §6).

## 5. Recul critique

- L'IA accélère l'écriture ; elle ne remplace pas la compréhension. Chaque membre de l'équipe doit pouvoir expliquer les extraits de code du document 04 §6 et les choix du document 03.
- Les textes d'accompagnement (besoins, conduite du changement) sont des propositions plausibles déduites du cahier des charges : ils doivent être relus et ajustés par l'équipe, qui connaît les échanges réels avec l'encadrant.
- Aucune donnée personnelle ni confidentielle n'a été transmise à l'outil : le projet ne contient que des données publiques et simulées.
