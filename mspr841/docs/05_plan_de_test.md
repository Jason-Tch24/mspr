# 05 — Plan de test et validation

> Compétence visée : *effectuer les tests de la solution pour identifier les erreurs et
> établir les plans de correction avant la mise en production.*

## 1. Stratégie

| Niveau | Objet | Outil | Automatisé | Où |
|---|---|---|---|---|
| Unitaire | Calcul des features, règles de seuils, store du dashboard | pytest | Oui | `mspr841/tests/test_features.py`, `dashboard/test_store.py`, `dashboard/test_health.py` |
| Intégration | API de scoring de bout en bout ; chaîne simulateur → store → KPI → alertes | pytest + FastAPI TestClient | Oui | `mspr841/tests/test_api.py`, `dashboard/test_pipeline_temps_reel.py` |
| Qualité des modèles | Non-régression des performances | pytest sur les métadonnées | Oui | `test_api.py` (cas Q01 à Q03) |
| Analyse statique | Erreurs de syntaxe, noms indéfinis | flake8 | Oui | CI |
| Système | Images Docker, démarrage de la stack, prédiction dans le conteneur | Docker Compose + curl | Oui | CI, job `docker` |
| Recette | Scénarios métier joués dans les dashboards | Manuel, cahier de recette (§5) | Non | Démonstration |

Outils retenus : **pytest** pour l'exécution, **FastAPI TestClient** pour appeler l'API sans
réseau, **GitHub Actions** pour rejouer la campagne à chaque modification et publier le
rapport `junit.xml`.

Lancement : `pytest` à la racine du dépôt (environ 15 secondes).

## 2. Jeux d'essai

| Jeu | Contenu | Utilisation |
|---|---|---|
| Données Gold versionnées | `data/gold/usine_*.parquet` (8 640 sessions par usine) | Rejouées par le simulateur dans les tests d'intégration |
| Régimes thermiques établis | 47 sessions identiques + la session courante, de 7,5 K à 15 K | Vérifier le sens et le niveau du risque (usine B) |
| Régimes contrastés | Même mesure courante (10,5 K) après 47 sessions à 8,5 K ou à 13,5 K | Vérifier que l'historique est pris en compte |
| Niveaux d'usure | 0, 5, 20, 40, 60, 80, 88, 90, 100 % | Vérifier la décroissance de la RUL et les seuils (usine A) |
| Entrées invalides | Valeurs hors bornes, champ manquant, mauvais type, corps vide | Vérifier le rejet `422` |
| Série aléatoire reproductible | 200 valeurs, graine fixe | Parité entre calcul d'entraînement et calcul de l'API |
| Pannes injectées | `store.inject_fault(...)` | Vérifier la réaction du moteur d'alertes et de l'IA |

## 3. Cas de test automatisés

### API — supervision

| Id | Cas | Donnée de test | Résultat attendu |
|---|---|---|---|
| API01 | Santé du service | `GET /` | `200`, `modeles_ok = true` |
| API02 | Métadonnées des modèles | `GET /models` | Type et horizon cohérents avec les règles |
| API03 | Règles exposées | `GET /regles` | Seuils identiques au fichier de configuration |

### Usine A — durée de vie de l'outil

| Id | Cas | Donnée de test | Résultat attendu |
|---|---|---|---|
| A01 | Outil neuf | usure 5 % | Niveau `OK`, RUL > 20 sessions |
| A02 | Outil usé | usure 88 % | Niveau `CRITICAL`, message « IMMINENT » |
| A03 | Cohérence physique | usure 0 → 90 % | RUL strictement décroissante, jamais négative |
| A04 | Conversion | usure 45 % | heures = sessions × 0,5 |
| A05 | Borne | usure 100 % | RUL = 0 |
| A06 | Entrées invalides (4 variantes) | usure 120 %, TRS 1,4, champ absent, texte | `422` |
| A07 | Seuils d'alerte (6 valeurs limites) | RUL 0 ; 10 ; 10,1 ; 20 ; 20,1 ; 60 | CRITICAL ; CRITICAL ; WARNING ; WARNING ; OK ; OK |

### Usine B — risque thermique

| Id | Cas | Donnée de test | Résultat attendu |
|---|---|---|---|
| B01 | Régime nominal | 13,5 K établi | Niveau `OK`, « Normal », 47 sessions utilisées |
| B02 | Dissipation dégradée | 7,8 K établi | Niveau `CRITICAL` |
| B03 | Cohérence physique | 15 → 7,5 K | Probabilité croissante quand le delta baisse |
| B04 | Mode dégradé | aucune session d'historique | `mode_degrade = true` |
| B05 | Prise en compte de l'historique | 10,5 K après régime bas / haut | Risque plus élevé après le régime bas |
| B06 | Cohérence des probabilités | 10 K | p entre 0 et 1, somme des deux classes = 1 |
| B07 | Historique trop long | 300 valeurs | Tronqué à 47 |
| B08 | Entrées invalides (3 variantes) | delta négatif, historique texte, corps vide | `422` |
| B09 | Seuils d'alerte | p autour de 0,45 et 0,65 | OK / WARNING / CRITICAL aux bonnes bornes |
| B10 | Compatibilité dashboard | charge utile complète du dashboard | `200` |

### Qualité des modèles (non-régression)

| Id | Cas | Résultat attendu |
|---|---|---|
| Q01 | Le modèle A bat la référence naïve | MAE < 20 % de la MAE de la moyenne |
| Q02 | Le modèle B fait mieux que le hasard | ROC-AUC ≥ 0,70 |
| Q03 | Les niveaux d'alerte sont ordonnés | Taux de panne observé : Normal < À risque < Critique |

### Features

| Id | Cas | Résultat attendu |
|---|---|---|
| F01 | Une seule valeur | Moyennes = valeur, tendance = 0 |
| F02 | Fenêtres 6 h et 24 h | Moyennes, minimum et tendance exacts |
| F03 | Série vide | Erreur explicite |
| F04 | Parité entraînement / API | Valeurs identiques sur 8 positions d'une série de 200 points |

### Dashboard

| Id | Cas | Résultat attendu |
|---|---|---|
| D01–D10 | Configuration et store (`test_health.py`) | Usines, ports, seuils, structures de données conformes |
| D11–D15 | Store (`test_store.py`) | Lecture/écriture, tampon, alertes, injection et retrait d'une panne, isolation par usine |
| D22–D24 | Filtre de clics des boutons d'injection (`test_ui_utils.py`) | Un rafraîchissement sans clic est ignoré ; un clic réel est identifié |
| D16–D21 | Pipeline temps réel (`test_pipeline_temps_reel.py`) | Le simulateur alimente le store ; KPI calculés ; moteur d'alertes sans erreur ; une panne injectée déclenche une alerte |

## 4. Résultats de la campagne

| Mesure | Résultat |
|---|---|
| Tests exécutés | 61 |
| Réussis | 61 |
| Échecs | 0 |
| Durée | ≈ 12 s |
| Analyse statique flake8 (E9, F) | 0 erreur |
| Build des images Docker | Réussi (API, dashboard) |
| Test système | API saine dans son conteneur ; dashboard B servi ; appel dashboard → API par le réseau interne vérifié |

Environnement : macOS, Python 3.13, puis rejoué sous Linux / Python 3.11 par la CI.

## 5. Cahier de recette (scénarios métier, manuels)

À jouer avec la stack démarrée (`docker compose up -d --build`).

| Id | Scénario | Étapes | Résultat attendu | Statut |
|---|---|---|---|---|
| R01 | Consulter la prédiction d'usure | Ouvrir http://localhost:8051, onglet AI Predictions | Jauge RUL, badge de niveau, phrase d'action, modèle affiché | ✅ 10/11/2026 |
| R02 | Outil en fin de vie | Cliquer « Usure critique (92 %) » | Badge CRITICAL, message « Remplacement outil IMMINENT » | ✅ 10/11/2026 |
| R03 | Retour à la normale | Cliquer « Reprendre simulateur » | Le badge revient au niveau du simulateur | ✅ 10/11/2026 |
| R04 | Consulter le risque thermique | Ouvrir http://localhost:8052, onglet AI Predictions | Niveau, probabilité sous 24 h, nombre de sessions analysées | ✅ 10/11/2026 |
| R05 | Dissipation dégradée | Cliquer « Dissipation dégradée (delta 9,2 K) » | Niveau « À risque », message de vérification du refroidissement | ✅ 10/11/2026 |
| R06 | Panne imminente | Cliquer « Panne imminente » (delta 7,6 K) | Niveau « Critique », probabilité proche de 80 %. La règle de supervision `derive_thermique` (limite à 5,9 K) ne se déclenche pas encore : l'IA signale le risque avant le franchissement du seuil | ✅ 10/11/2026 |
| R07 | IA indisponible | `docker compose stop api`, recharger l'onglet | Message « API indisponible », les autres onglets fonctionnent | ✅ 10/11/2026 |
| R08 | Reprise de l'IA | `docker compose start api` | L'onglet IA affiche de nouveau une prédiction, sans redémarrer le dashboard | ✅ 10/11/2026 |
| R09 | Changer un seuil | Passer `seuil_warning` à 0,30 dans `regles_metier.json`, reconstruire l'API | Davantage de sessions classées « À risque » | ☐ à jouer |
| R10 | Vue direction | Ouvrir http://localhost:8050 | Les trois usines et leur statut | ✅ 10/11/2026 |

Les scénarios R01 à R08 et R10 ont été déroulés à l'écran dans Chrome le 10/11/2026, sur la
stack Docker complète. R09 (changement de seuil) reste à jouer. L'équipe doit rejouer
l'ensemble avant la soutenance, sur la machine de démonstration.

## 6. Anomalies détectées et corrections

| Anomalie | Détection | Gravité | Correction | Vérification |
|---|---|---|---|---|
| Le modèle B classait un delta nominal en « Critique » et un delta extrême en « Normal » | Appels manuels à l'API pendant l'audit | Bloquante | Reformulation de la cible, features partagées, historique transmis | B01 à B05 |
| Écart entre variables d'entraînement et variables reçues par l'API (lags remplacés par des constantes) | Lecture du code | Majeure | Module `features.py` commun | F04 |
| Scénario de démonstration « Surchauffe 20 K » contraire à la physique simulée | Analyse des données | Majeure | Presets ramenés à 9,2 K et 7,6 K | R05, R06 |
| Modèles exclus de Git : l'image Docker démarrait sans modèle | Lecture du Dockerfile | Majeure | Modèles versionnés ; healthcheck exigeant `modeles_ok` | Job `docker` de la CI |
| Adresse de l'API écrite en dur (`localhost`) : dashboards incapables de joindre l'API en conteneur | Lecture du code | Majeure | Variable `MECHA_API_URL` | Test système |
| Conteneur API en échec : fichiers illisibles par l'utilisateur non privilégié | Test système local | Majeure | `COPY --chown` dans le Dockerfile | Test système |
| Une panne s'injectait seule à l'ouverture de l'onglet IA (usine B) et « Reprendre simulateur » restait sans effet ; à l'usine A, la panne injectée était effacée au rafraîchissement suivant | Recette à l'écran (R03, R05) | Bloquante pour la démonstration | Seul un clic réel (`n_clicks` > 0) est pris en compte : `dashboard/ui_utils.py` | `test_ui_utils.py`, R02 à R06 rejoués |
| Tests du dashboard écrits comme scripts : aucune assertion comptée par pytest | Lecture des tests | Mineure | Réécriture en fonctions `test_*` avec fixture de simulateur | D11 à D21 |
| Version de scikit-learn différente entre l'entraînement et `requirements.txt` | Comparaison des versions | Mineure | Version alignée (1.8.0) et tracée dans les métadonnées | Job `train` de la CI |

## 7. Validation de la solution

### Critères techniques

| Critère | Seuil | Résultat | Verdict |
|---|---|---|---|
| Erreur du modèle A | MAE ≤ 2 sessions (1 h) | 1,05 session | ✅ |
| Discrimination du modèle B | ROC-AUC ≥ 0,70 | 0,74 | ✅ |
| Cohérence des niveaux d'alerte | Taux de panne croissant avec le niveau | 28 % / 58 % / 69 % | ✅ |
| Tests automatisés | 100 % réussis | 61 / 61 | ✅ |
| Démarrage en conteneur | API saine, dashboards servis | Vérifié | ✅ |
| Résistance à l'indisponibilité de l'IA | Dashboard utilisable | Vérifié par le code et R07 | ✅ |

### Critères fonctionnels

| Critère (issu des besoins, document 01) | Verdict |
|---|---|
| Une durée restante est affichée pour l'outil (BF1) | ✅ |
| Un niveau normal / à risque est affiché, avec une action (BF2, BF3) | ✅ |
| Les seuils sont réglables sans développement (BF4) | ✅ |
| Les résultats sont dans les dashboards existants (BF5) | ✅ |
| Une dégradation peut être simulée (BF6) | ✅ |
| Les prédictions sont historisées (BF9) | ❌ non réalisé |

### Réserves

La validation porte sur des données simulées. Elle établit que la chaîne fonctionne de bout
en bout et que les modèles se comportent de façon cohérente ; elle **n'établit pas** leur
performance sur les machines de MECHA. Une phase pilote sur un site, avec des données
réelles et un suivi des alertes confirmées ou non par la maintenance, est le préalable à
tout déploiement (document 06).
