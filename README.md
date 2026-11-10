# MECHA — Pilotage industriel et maintenance prédictive

Projet MSPR EPSI (I1 EISI IA, RNCP 35584) pour l'entreprise fictive MECHA.

- **TPRE831 (bloc 3)** : pipeline de données Bronze / Silver / Gold et dashboards temps réel.
- **TPRE841 (bloc 4)** : solution d'IA de maintenance prédictive, exposée par une API et
  intégrée aux dashboards métiers, conteneurisée et testée en intégration continue.

## Ce que fait la solution

| Usine | Question métier | Réponse de l'IA |
|---|---|---|
| A — Lyon | Dans combien de temps faut-il changer l'outil de coupe ? | Durée de vie résiduelle (RUL), en sessions de 30 min et en heures |
| B — Bordeaux | Cette machine risque-t-elle une panne thermique dans les 24 h ? | Probabilité de panne et niveau Normal / À risque / Critique |

Les résultats sont affichés dans l'onglet **AI Predictions** des dashboards des usines A et B.

## Démarrage rapide (Docker)

```bash
docker compose up -d --build
```

| Service | Adresse |
|---|---|
| API de scoring (documentation interactive) | http://localhost:8000/docs |
| Dashboard Groupe | http://localhost:8050 |
| Dashboard Usine A | http://localhost:8051 |
| Dashboard Usine B | http://localhost:8052 |
| Dashboard Usine C | http://localhost:8053 |

Arrêt : `docker compose down`.

## Démarrage sans Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Terminal 1 — API
cd mspr841/api && uvicorn main:app --port 8000

# Terminal 2 — un dashboard
cd dashboard && python app_usine_B.py
```

## Tests et entraînement

```bash
pytest                                  # 58 tests : API, features, règles, dashboard
python mspr841/ml/train_models.py       # ré-entraîne et compare les modèles
flake8 dashboard/ mspr841/ --select=E9,F --extend-ignore=F401,F841
```

La CI GitHub Actions (`.github/workflows/ci.yml`) rejoue ces étapes à chaque push,
ré-entraîne les modèles, construit les images Docker et teste l'API dans son conteneur.

## Organisation du dépôt

```
data/                 Données : source AI4I 2020, Bronze, Silver, Gold (3 usines)
notebooks/            Pipeline Medallion (00 à 04) et premières explorations ML (bloc 3)
dashboard/            Dashboards Dash : groupe + usines A, B, C ; simulateur, KPI, alertes
mspr841/
  api/                API FastAPI : main.py, schemas.py, features.py
    regles_metier.json   Seuils d'alerte et messages (paramétrage sans code)
    models/              Modèles entraînés + métadonnées et métriques
  ml/train_models.py  Entraînement, comparaison et sélection des modèles
  tests/              Tests de l'API et des features
  docs/               Dossier du bloc 4 (voir ci-dessous)
reports/              Benchmark des modèles (benchmark_841.json)
docker-compose.yml    Stack complète : API + 4 dashboards
```

## Documentation du bloc 4

| Document | Contenu |
|---|---|
| [01 — Besoins métiers](mspr841/docs/01_besoins_metiers.md) | Guide d'entretien, questionnaire, synthèse des besoins et contraintes |
| [02 — Architecture](mspr841/docs/02_architecture.md) | Schéma, composants, flux, choix justifiés, tolérance aux pannes |
| [03 — Données et modèles](mspr841/docs/03_donnees_et_modeles.md) | Jeux de données, dictionnaire, modèles étudiés, résultats, limites, RGPD |
| [04 — Solution applicative](mspr841/docs/04_solution_applicative.md) | Intégration IA ↔ application, paramétrage, règles métier, écrans |
| [05 — Plan de test](mspr841/docs/05_plan_de_test.md) | Stratégie, cas de test, jeux d'essai, résultats, validation |
| [06 — Déploiement et intégration continue](mspr841/docs/06_deploiement_et_ci.md) | Docker, CI, exploitation, projection multi-sites |
| [07 — Conformité et guide utilisateur](mspr841/docs/07_conformite_et_guide_utilisateur.md) | Cahier des charges ↔ réalisation, guide métier |
| [08 — Conduite du changement](mspr841/docs/08_conduite_du_changement.md) | Acteurs, plan d'action, formation, déploiement progressif |
| [09 — Usage de l'IA générative](mspr841/docs/09_usage_ia_generative.md) | Prompts utilisés et vérifications effectuées |

## Limite à garder en tête

Toutes les données sont publiques (AI4I 2020) ou simulées : aucune donnée réelle de MECHA.
Les performances annoncées valent pour ces données et devront être réévaluées sur des
mesures terrain avant toute mise en production.
