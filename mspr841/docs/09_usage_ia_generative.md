# 09 — Usage de l'intelligence artificielle générative

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

**Prompt 1 — audit**

> je vais faire un projet MSPR je veux le finaliser c'est dans le répertoire que je vais
> t'envoyer en fait c'est le bloc quatre qu'il faut développer analyse les documents qui
> sont à l'intérieur tu fais un audit de ce qui est déjà fait, et dis-moi ce qu'il reste à
> faire pour finaliser le bloc quatre

Résultat : tableau d'avancement par compétence de la grille, liste des problèmes du code,
liste des livrables manquants, ordre de travail proposé.

**Prompt 2 — réalisation**

> vas-y fais toutes les étapes et place le code sur github

Résultat : les modifications décrites dans ce dossier.

> **À compléter par l'équipe** : les prompts des sessions précédentes (pipeline, dashboards,
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
| Chiffres cités dans la documentation | Relus dans les fichiers produits (`benchmark_841.json`, rapports Silver, limites SPC) | Deux affirmations corrigées après vérification |

## 4. Ce qui a été adapté ou écarté

- **Proposition initiale conservée après contrôle** : sélection du modèle le plus simple à performance équivalente. La tolérance a été fixée à 1 % ; avec 2 %, le modèle B retenu aurait ignoré l'historique thermique.
- **Écarté** : conserver trois classes pour l'usine B. La classe « panne dans les 3 sessions » n'est pas prévisible sur ces données.
- **Écarté** : annoncer qu'une alerte de supervision se déclenche dans le scénario « Panne imminente ». La limite de contrôle réelle (5,9 K) est plus basse que la valeur injectée (7,6 K) ; le plan de recette a été corrigé.
- **Signalé comme non fait** : les entretiens avec les métiers sont simulés, et le compte-rendu des échanges avec l'encadrant reste à remplir avec des échanges réels (document 01 §6).

## 5. Recul critique

- L'IA accélère l'écriture ; elle ne remplace pas la compréhension. Chaque membre de l'équipe doit pouvoir expliquer les extraits de code du document 04 §6 et les choix du document 03.
- Les textes d'accompagnement (besoins, conduite du changement) sont des propositions plausibles déduites du cahier des charges : ils doivent être relus et ajustés par l'équipe, qui connaît les échanges réels avec l'encadrant.
- Aucune donnée personnelle ni confidentielle n'a été transmise à l'outil : le projet ne contient que des données publiques et simulées.
