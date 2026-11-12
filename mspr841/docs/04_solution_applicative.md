# 04 — Solution applicative d'exploitation des résultats IA

> Compétences visées : *développer une application adaptée à l'environnement technique* et
> *développer une solution intégrée par le paramétrage et un langage de configuration.*

## 1. Principe

Les modèles ne sont jamais consultés directement. Leurs résultats passent par trois étages :

1. **le modèle** produit une valeur brute (une durée, une probabilité) ;
2. **les règles métier** la transforment en niveau d'alerte et en message d'action ;
3. **le dashboard** l'affiche à côté des indicateurs que l'équipe suit déjà.

Le technicien lit « Machine à risque — vérifier le circuit de refroidissement dans le
poste », pas « p = 0,58 ».

## 2. Mécanismes d'intégration

| Échange | Mécanisme | Format |
|---|---|---|
| Dashboards → IA | Appel HTTP `POST` à l'API de scoring, délai maximal 2 s | JSON |
| IA → dashboards | Réponse synchrone | JSON |
| Entraînement → API | Fichiers de modèle et de métadonnées | joblib + JSON |
| Données Gold → dashboards et entraînement | Lecture de fichiers | Parquet |
| Paramétrage → API | Fichier de règles lu au démarrage | JSON |
| Paramétrage → dashboards | Variable d'environnement `MECHA_API_URL`, constantes de `config.py` | texte, Python |

### Contrat de l'API

Documentation interactive générée automatiquement : `http://localhost:8000/docs`.

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/` | Santé du service et des modèles |
| GET | `/models` | Modèle retenu, métriques, benchmark, limites connues |
| GET | `/regles` | Règles métier actives |
| POST | `/predict/rul` | Durée de vie résiduelle de l'outil (Usine A) |
| POST | `/predict/risque-thermique` | Risque de panne thermique à 24 h (Usine B) |

**Exemple — Usine A**

```bash
curl -X POST http://localhost:8000/predict/rul \
  -H 'Content-Type: application/json' \
  -d '{"usure_cumulee_pct": 88, "TRS": 0.9}'
```

```json
{
  "usine": "Usine_A",
  "rul_sessions": 2.2,
  "rul_heures": 1.1,
  "usure_cumulee_pct": 88.0,
  "niveau_alerte": "CRITICAL",
  "interpretation": "Remplacement outil IMMINENT — 2 session(s) restante(s) (1.1 h). Planifier l'intervention maintenant.",
  "modele": "Linéaire sur l'usure seule · MAE=1.052 sessions · R²=0.996"
}
```

**Exemple — Usine B**

```bash
curl -X POST http://localhost:8000/predict/risque-thermique \
  -H 'Content-Type: application/json' \
  -d '{"temp_process_delta": 7.8, "historique_delta": [7.9, 7.8, 8.0]}'
```

```json
{
  "usine": "Usine_B",
  "probabilite_panne_24h": 0.802,
  "risque_label": 2,
  "risque_nom": "Critique",
  "probabilites": {"Normal": 0.198, "À risque": 0.802},
  "niveau_alerte": "CRITICAL",
  "interpretation": "Risque thermique CRITIQUE — probabilité de panne sous 24 h : 80%. Contrôler le refroidissement sans attendre.",
  "mode_degrade": false,
  "nb_sessions_historique": 3,
  "modele": "Régression logistique · AUC=0.813 · PR-AUC=0.74"
}
```

Codes de retour : `200` prédiction ; `422` entrée invalide (champ manquant, hors bornes,
mauvais type) ; `503` modèles non chargés.

## 3. Paramétrage applicatif

### 3.1 Règles de l'IA — `mspr841/api/regles_metier.json`

C'est le formalisme de configuration de la solution : un fichier JSON lu par l'API au
démarrage. Le modifier ne demande **ni développement ni ré-entraînement**.

```json
{
  "session_duree_min": 30,
  "usine_A": {
    "rul_critical_sessions": 10,
    "rul_warning_sessions": 20,
    "messages": {
      "CRITICAL": "Remplacement outil IMMINENT — {rul:.0f} session(s) restante(s) ({heures:.1f} h). Planifier l'intervention maintenant."
    }
  },
  "usine_B": {
    "horizon_sessions": 48,
    "seuil_warning": 0.45,
    "seuil_critical": 0.65,
    "noms": {"OK": "Normal", "WARNING": "À risque", "CRITICAL": "Critique"}
  }
}
```

| Paramètre | Valeur | Effet | Qui le règle |
|---|---|---|---|
| `usine_A.rul_critical_sessions` | 10 (5 h) | En dessous : alerte CRITICAL | Responsable maintenance |
| `usine_A.rul_warning_sessions` | 20 (10 h) | En dessous : alerte WARNING | Responsable maintenance |
| `usine_B.seuil_warning` | 0,45 | Probabilité à partir de laquelle la machine est « À risque » | Responsable maintenance |
| `usine_B.seuil_critical` | 0,65 | Probabilité à partir de laquelle le risque est « Critique » | Responsable maintenance |
| `usine_B.horizon_sessions` | 48 (24 h) | Horizon de prédiction — **changer cette valeur impose un ré-entraînement** | Équipe data |
| `messages.*` | texte à trous | Phrase d'action affichée ; `{rul}`, `{heures}`, `{proba}` sont remplacés par les valeurs | Maintenance + qualité |

**Règle de transformation** appliquée par l'API :

```
Usine A :  RUL ≤ 10 sessions → CRITICAL ;  RUL ≤ 20 → WARNING ;  sinon OK
           heures = sessions × session_duree_min / 60
Usine B :  p ≥ 0,65 → CRITICAL (Critique) ;  p ≥ 0,45 → WARNING (À risque) ;  sinon OK (Normal)
```

**Comment choisir les seuils de l'usine B.** Baisser `seuil_warning` détecte plus de pannes
mais multiplie les alertes. Le tableau « des probabilités aux niveaux d'alerte » du
document 03 donne, pour les seuils actuels, la part de sessions en alerte et le taux de
panne réellement observé ; il est recalculé à chaque entraînement et consultable par
`GET /models` (clé `lecture_metier_des_seuils`).

Un autre fichier de règles peut être fourni par site grâce à la variable
`MECHA_REGLES_PATH`, sans reconstruire l'image.

### 3.2 Règles de supervision — `dashboard/config.py`

Les alertes temps réel du bloc 3 sont décrites de façon déclarative dans `ALERT_RULES`.
Chaque règle est un dictionnaire, interprété par le moteur `alert_engine.py` :

```python
'derive_thermique': {
    'kpi'         : 'temp_process_delta',     # indicateur surveillé
    'condition'   : 'below',                  # sens du franchissement
    'seuil_src'   : 'json',                   # seuil lu dans les limites SPC
    'seuil_key'   : 'temp_process_delta.lcl', # limite de contrôle inférieure
    'severite'    : 'WARNING',
    'cooldown_s'  : 300,                      # délai avant une nouvelle alerte
    'persistence' : 3,                        # sessions consécutives exigées
    'label'       : 'Dérive Thermique',
    'message'     : "Le delta thermique process/air descend sous la limite critique. ..."
}
```

| Règle | Indicateur | Sévérité |
|---|---|---|
| `derive_qualite` | Taux de rebut au-dessus de la limite de contrôle | WARNING |
| `machine_arretee` | Panne machine | CRITICAL |
| `derive_cycle` | Dérive du temps de cycle > 20 % | WARNING |
| `rupture_appro` | Rupture d'approvisionnement | CRITICAL |
| `usure_warning` / `usure_critique` | Usure outil ≥ 75 % / ≥ 90 % | INFO / CRITICAL |
| `derive_thermique` | Delta thermique sous la limite de contrôle | WARNING |
| `trs_critique` | TRS < 75 % | CRITICAL |

Les limites de contrôle (moyenne ± 3 écarts-types, calculées sur janvier 2024, hors pannes)
sont dans `data/gold/limites_usine_*.json`.

**Complémentarité.** Les règles de supervision réagissent à ce qui **se passe** (un seuil
est franchi maintenant) ; l'IA estime ce qui **va se passer** (risque sous 24 h, durée
restante). Les deux sont affichées dans le même dashboard.

### 3.3 Fréquences de mise à jour

| Élément | Fréquence | Paramètre |
|---|---|---|
| Nouvelle session rejouée par le simulateur | toutes les 10 s | `SIMULATION_INTERVAL_S` |
| Rafraîchissement de l'écran et appel à l'API | toutes les secondes | `dcc.Interval` des dashboards |
| Historique thermique transmis à l'IA | 47 sessions + la session courante (24 h) | `_HISTORIQUE_SESSIONS` |
| Tampon de sessions en mémoire | 1 152 sessions | `BUFFER_SIZE_SESSIONS` |
| Ré-entraînement des modèles | à la demande, et à chaque push en CI | `train_models.py` |

En production, la fréquence d'appel à l'IA serait alignée sur l'arrivée d'une nouvelle
session (30 min), et non sur le rafraîchissement de l'écran.

## 4. Écrans métiers

### Navigation commune

Les quatre tableaux de bord partagent le même habillage (`dashboard/shell.py`, `dashboard/assets/app.css`) :
une barre de navigation **Groupe · Usine A · Usine B · Usine C** présente sur chaque écran, avec
un point de couleur qui donne l'état de chaque site (vert : normal, orange : à surveiller,
rouge : critique). Depuis la vue groupe (port 8050), un clic sur la fiche d'un site ouvre le
tableau de bord de l'usine dans le même onglet. Tous les libellés sont en français.

### Dashboards par usine (ports 8051, 8052, 8053)

| Onglet | Contenu | Utilisateur principal | Usage |
|---|---|---|---|
| Vue d’ensemble | TRS, disponibilité, performance, qualité, état des 4 machines | Responsable de production | Voir en un coup d'œil si la ligne tient ses objectifs |
| Maintenance | Usure outil, pannes, durées d'arrêt | Technicien, responsable maintenance | Suivre l'état des équipements |
| Qualité | Taux de rebut, limites de contrôle, dérives | Direction qualité | Détecter une dérive avant la non-conformité |
| Alertes | Alertes actives et historique | Tous | Savoir ce qui demande une action |
| **Prédictions IA** | Prédiction du modèle, niveau d'alerte, message d'action, mesures utilisées, modèle et sa performance | Technicien, responsable maintenance | **Décider d'une intervention avant la panne** |

### Onglet Prédictions IA — Usine A

- Jauge de durée de vie résiduelle (sessions et heures).
- Badge OK / WARNING / CRITICAL et phrase d'action.
- Mesures envoyées au modèle (usure, TRS, temps de cycle…).
- Démonstration : « Usure critique (92 %) », « Arrêt production », « Reprendre le simulateur ».

### Onglet Prédictions IA — Usine B

- Niveau de risque (Normal / À risque / Critique) et probabilité de panne sous 24 h.
- Nombre de sessions d'historique analysées.
- Phrase d'action et mesures courantes.
- Démonstration : « Dissipation dégradée (delta 9,2 K) », « Panne imminente » (7,6 K), « Reprendre le simulateur ».

### Dashboard Groupe (port 8050)

Vue consolidée des trois usines pour la direction industrielle : TRS par site, statut global,
accès à chaque dashboard d'usine.

## 5. Usages attendus

| Moment | Acteur | Action dans l'outil | Décision |
|---|---|---|---|
| Prise de poste | Technicien de maintenance | Ouvre l'onglet Prédictions IA de son usine | Liste les machines à contrôler en priorité |
| Niveau « À risque » (usine B) | Technicien | Lit le message, contrôle le refroidissement | Intervention légère dans le poste |
| Niveau « Critique » (usine B) | Responsable maintenance | Vérifie la tendance thermique dans Maintenance | Arrêt planifié plutôt que subi |
| RUL < 20 sessions (usine A) | Responsable de production | Consulte la durée restante | Place le changement d'outil à un changement de série |
| RUL < 10 sessions (usine A) | Technicien | Prépare l'outil de rechange | Remplacement avant la casse |
| Revue hebdomadaire | Direction industrielle | Dashboard Groupe | Compare les sites, arbitre les moyens |

## 6. Logique de développement : lecture de code pour la démonstration

Trois extraits à commenter en soutenance.

**a. Une seule définition des variables** (`mspr841/api/features.py`) — utilisée par
l'entraînement *et* par l'API, ce qui garantit que le modèle reçoit en service ce qu'il a
appris :

```python
def thermal_features_from_series(valeurs: list[float]) -> dict[str, float]:
    court = valeurs[-FENETRE_COURTE:]      # 12 sessions = 6 h
    long_ = valeurs[-FENETRE_LONGUE:]      # 48 sessions = 24 h
    moy_court = sum(court) / len(court)
    moy_long = sum(long_) / len(long_)
    return {
        "delta": float(valeurs[-1]),
        "delta_moy_6h": float(moy_court),
        "delta_moy_24h": float(moy_long),
        "delta_min_6h": float(min(court)),
        "delta_tendance": float(moy_court - moy_long),   # négatif = le delta baisse
    }
```

**b. Du score à la décision** (`mspr841/api/main.py`) — le modèle donne une probabilité,
le paramétrage donne le niveau :

```python
def niveau_alerte_risque(proba: float) -> str:
    regles = REGLES["usine_B"]
    if proba >= regles["seuil_critical"]:
        return "CRITICAL"
    if proba >= regles["seuil_warning"]:
        return "WARNING"
    return "OK"
```

**c. Tolérance aux pannes côté application** (`dashboard/app_usine_B.py`) — l'IA est un
plus, jamais un point de blocage :

```python
try:
    resp = requests.post(_AI_API_URL_B, json=payload, timeout=2)
    ...
except Exception as e:
    err_msg = f"API indisponible ({config.API_BASE_URL}) — {type(e).__name__}"
```

## 7. Note sur la compétence « progiciel intégré »

La grille évoque le paramétrage d'un progiciel (SAP, Dynamics, Salesforce) et son langage
propre. Le cahier des charges de MECHA ne comporte pas de progiciel : il demande d'illustrer
« un langage ou formalisme de configuration (requêtes, scripts, règles métiers, formats
d'échange) ». La réponse apportée est le paramétrage déclaratif décrit ci-dessus
(`regles_metier.json`, `ALERT_RULES`) et le contrat JSON de l'API, conçu pour être consommé
par un MES, une GMAO ou un ERP. Le branchement à la GMAO (création automatique d'un ordre
de travail au niveau « Critique ») est la première évolution prévue.
