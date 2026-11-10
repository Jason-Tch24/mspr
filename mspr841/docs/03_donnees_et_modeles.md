# 03 — Données et modèles

## 1. Origine des données

| Couche | Fichier | Contenu | Origine |
|---|---|---|---|
| Source | `data/source/ai4i2020.csv` | 10 000 lignes, 14 colonnes | Jeu public **AI4I 2020 Predictive Maintenance** (UCI) |
| Bronze | `data/bronze/ai4i_raw.csv`, `ai4i_raw_dirty.csv` | Copie brute + version dégradée volontairement | Script `notebooks/00_bronze.ipynb` |
| Silver | `data/silver/ai4i_clean.parquet` | Données nettoyées et contrôlées | `notebooks/01_silver.ipynb` |
| Gold | `data/gold/usine_A.parquet`, `usine_B.parquet`, `usine_C.parquet` | 8 640 sessions de 30 min par usine (du 01/01/2024 au 29/06/2024) | `notebooks/02` à `04` |

Aucune donnée réelle de MECHA n'est utilisée, conformément au cahier des charges.

### Défauts injectés en Bronze (`data/bronze/injection_log.json`)

| Défaut | Volume | Traitement en Silver |
|---|---|---|
| Valeurs manquantes | 200 (50 par colonne capteur) | Imputation par la médiane de la colonne |
| Doublons | 20 lignes | Suppression |
| Catégories mal formées (`X`, `low`, `MED`, `?`) | 15 lignes | Lignes écartées |
| Valeurs hors plage (vitesse à −50, 3 500, 9 999 tr/min) | 10 lignes | Écrêtage aux bornes physiques (0 à 3 000 tr/min) |

Bilan Silver (`data/silver/silver_quality_report.json`) : 10 020 lignes en entrée, 9 985 en sortie, aucune valeur manquante restante.

### Hypothèses de simulation (couche Gold)

Le jeu AI4I n'est pas une série temporelle. Pour obtenir un historique exploitable, les
distributions de ses capteurs servent de base à une simulation de 180 jours par usine,
chacune avec un problème dominant.

| Usine | Problème simulé | Règles de simulation |
|---|---|---|
| A — Lyon | Usure progressive de l'outil | L'usure augmente à chaque session d'un incrément aléatoire dépendant du type de pièce ; l'outil est remplacé à la limite ; le rebut augmente avec l'usure. |
| B — Bordeaux | Pannes thermiques groupées | Delta thermique = 11,5 K − 2,5 × sinus (période 45 jours) + bruit (σ = 0,5 K). Pannes tirées selon un processus de Poisson dont le taux suit la même sinusoïde et est multiplié par 3 sous 8,6 K. |
| C — Toulouse | Instabilité du process | Non utilisée par les modèles du bloc 4. |

### Limites connues des données

- **Volume** : 6 mois, 4 machines par usine, 111 pannes thermiques (usine B) et 115 remplacements d'outil (usine A).
- **Simplifications** : une seule cause dominante par usine ; pas d'effet de l'opérateur, de la matière ou de la saison.
- **Biais** : l'usure est quasi linéaire et les pannes thermiques sont, par construction, en partie aléatoires. Les scores ci-dessous reflètent ces règles, pas le comportement de machines réelles.
- **Session** : les données sont à la maille de 30 minutes ; aucun signal haute fréquence (vibrations).

## 2. Dictionnaire de données (couche Gold)

| Colonne | Type | Unité / domaine | Signification |
|---|---|---|---|
| `timestamp` | date-heure | pas de 30 min | Début de la session |
| `usine_id` | texte | Usine_A / B / C | Site |
| `machine_id` | texte | M01 à M04 | Machine |
| `type_piece` | texte | REF01 à REF04 | Référence produite |
| `equipe` | texte | Matin / Apres-midi / Nuit | Équipe en poste |
| `temp_air_c` | décimal | °C, ≈ 18 à 29 | Température ambiante |
| `temp_process_c` | décimal | °C, ≈ 27 à 42 | Température du process |
| `temp_process_delta` | décimal | K, ≈ 7,5 à 15,5 | Écart process − air. **Un delta bas signale une mauvaise dissipation de chaleur.** |
| `delta_ma` (usine B) | décimal | K | Moyenne mobile du delta sur 100 sessions |
| `vitesse_rotation_rpm` | entier | tr/min, ≈ 1 250 à 1 850 | Vitesse de broche |
| `couple_nm` | décimal | N·m, 20 à 70 | Couple de coupe |
| `usure_outil_min` | décimal | minutes | Temps d'usage cumulé de l'outil |
| `usure_cumulee_pct` | décimal | %, 0 à 90 | Usure rapportée à la durée de vie de l'outil |
| `remplacement_outil` | 0/1 | — | Outil remplacé pendant la session |
| `panne_machine` | 0/1 | — | Une panne, toutes causes |
| `panne_thermique`, `panne_usure_outil`, `panne_puissance`, `panne_surcharge`, `panne_aleatoire` | 0/1 | — | Cause de la panne |
| `type_panne` | texte | Aucune, Thermique, Usure outil… | Libellé de la cause |
| `duree_arret_min` | décimal | minutes | Durée de l'arrêt |
| `nb_pannes_7j` | entier | — | Pannes sur les 7 jours glissants |
| `intervention_maintenance` | 0/1 | — | Intervention réalisée |
| `temps_cycle_min` | décimal | minutes | Temps de cycle mesuré |
| `derive_cycle_pct` | décimal | % | Écart au temps de cycle nominal |
| `pieces_produites`, `pieces_rebutees` | entier | pièces | Production de la session |
| `taux_rebut` | décimal | 0 à 1 | Part de pièces rebutées |
| `indice_stabilite_process` | décimal | 0 à 1 | 1 = process stable |
| `consommation_kwh` | décimal | kWh | Énergie de la session |
| `rupture_appro` | 0/1 | — | Rupture d'approvisionnement |
| `disponibilite`, `performance`, `qualite` | décimal | 0 à 1 | Composantes du TRS |
| `TRS` | décimal | 0 à 1 | Taux de rendement synthétique |
| `TRS_7j` | décimal | 0 à 1 | TRS moyen sur 7 jours |

## 3. Démarche de modélisation

La même démarche est appliquée aux deux cas (`mspr841/ml/train_models.py`).

1. **Cible** construite uniquement à partir du futur de la série.
2. **Variables** définies une seule fois dans `features.py`, utilisées à l'entraînement et par l'API.
3. **Comparaison** de plusieurs modèles, dont des références simples, comme le demande le sujet.
4. **Validation temporelle** « walk-forward » (`TimeSeriesSplit`, 5 plis) : on entraîne toujours sur le passé et on teste sur le futur. Un découpage aléatoire laisserait le modèle « voir » le futur.
5. **Sélection par parcimonie** : on retient le modèle le plus simple dont la performance est à moins de 1 % du meilleur.
6. **Ré-entraînement** sur tout l'historique, export du modèle et de ses métadonnées.

## 4. Usine A — durée de vie résiduelle de l'outil (régression)

- **Cible** : nombre de sessions avant le prochain remplacement d'outil.
- **Variables** : 11 mesures instantanées (usure cumulée, TRS, temps de cycle, dérive, disponibilité, performance, qualité, consommation, vitesse, couple, taux de rebut).
- **Volume** : 8 464 sessions.

| Modèle | MAE (sessions) | RMSE | R² |
|---|---|---|---|
| Moyenne (référence naïve) | 18,39 | 21,25 | 0,000 |
| **Linéaire sur l'usure seule** ✅ | **1,05** | 1,35 | 0,996 |
| Ridge (11 variables) | 1,05 | 1,35 | 0,996 |
| Random Forest | 1,09 | 1,41 | 0,996 |
| Gradient Boosting | 1,08 | 1,38 | 0,996 |

**Interprétation.** L'erreur moyenne est d'environ une session, soit 30 minutes. Les modèles
complexes n'apportent rien : la durée de vie se déduit presque entièrement de l'usure
cumulée. Le modèle retenu est donc le plus simple, et le plus facile à expliquer à un
technicien (« chaque point d'usure consomme une durée connue »).

**Limite.** Ce R² très élevé vient de la simulation, où l'usure progresse presque
linéairement. Sur des machines réelles (usure non linéaire, casse brutale, changement de
matière), il faudra s'attendre à une erreur nettement plus forte et les modèles non
linéaires redeviendront pertinents.

## 5. Usine B — risque de panne thermique à 24 h (classification)

- **Cible** : « à risque » = au moins une panne thermique dans les 48 sessions suivantes (24 h). La session courante est exclue : on prédit, on ne constate pas.
- **Variables** : 5 indicateurs du régime thermique — delta courant, moyenne 6 h, moyenne 24 h, minimum 6 h, tendance (moyenne 6 h − moyenne 24 h).
- **Volume** : 8 592 sessions, dont 41 % « à risque ».
- **Validation** : 5 plis temporels séparés par un intervalle de 48 sessions, pour qu'aucune session d'entraînement ne recouvre le futur du pli de test.

| Modèle | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|
| Fréquence de base (référence naïve) | 0,500 | 0,409 | 0,244 |
| Régression logistique sur le delta instantané | 0,725 | 0,597 | 0,212 |
| **Régression logistique (5 variables)** ✅ | **0,738** | **0,609** | **0,211** |
| Random Forest | 0,657 | 0,547 | 0,254 |
| Gradient Boosting | 0,679 | 0,577 | 0,245 |

**Interprétation.** La régression logistique est à la fois la meilleure et la plus stable
d'un pli à l'autre ; les ensembles d'arbres sur-apprennent sur ce petit volume. Le modèle
se comporte comme attendu physiquement : la probabilité de panne augmente quand le delta
thermique baisse (0,05 à 15,5 K ; 0,33 au nominal de 11,5 K ; 0,80 à 7,6 K, en régime établi).

### Des probabilités aux niveaux d'alerte

Les seuils sont du paramétrage applicatif (`regles_metier.json`), pas une propriété du
modèle. Lecture sur les prédictions de validation :

| Niveau | Seuil | Part des sessions | Taux de panne réellement observé dans les 24 h |
|---|---|---|---|
| Normal | p < 0,45 | 63 % | 28 % |
| À risque | 0,45 ≤ p < 0,65 | 17 % | 58 % |
| Critique | p ≥ 0,65 | 20 % | 69 % |

À partir du niveau « À risque », l'alerte détecte 57 % des périodes suivies d'une panne
(rappel) et se vérifie 63 % du temps (précision).

**Limite.** Le modèle estime un **niveau de risque**, pas l'instant d'une panne : dans les
données simulées, les pannes sont tirées au hasard et seul leur taux dépend du régime
thermique. Même au niveau « Normal », 28 % des périodes de 24 h contiennent une panne. Le
modèle sert donc à **prioriser** les contrôles, pas à remplacer la maintenance préventive.
Un recalibrage sur données terrain est indispensable.

### Ce qui a été corrigé par rapport au premier PoC

Le premier modèle (3 classes « Normal / Risque / Critique », exactitude équilibrée de 0,45)
classait un delta nominal en « Critique » et un delta extrême en « Normal ». Trois causes :

1. la classe « Critique » (panne dans les 3 sessions) n'était pas prévisible, les pannes étant aléatoires à cet horizon ;
2. l'API ne recevait pas les variables d'historique et les remplaçait par des constantes, jamais vues à l'entraînement ;
3. le scénario de démonstration injectait un delta de 20 K, alors que le risque apparaît quand le delta **baisse**.

La cible a été reformulée en « normal / à risque » comme le demande le cahier des charges,
l'historique est maintenant transmis par le dashboard, et les features sont partagées.

## 6. Reproduire les résultats

```bash
pip install -r mspr841/ml/requirements.txt
python mspr841/ml/train_models.py
```

Sorties : `mspr841/api/models/*.joblib`, `*_meta.json` (paramètres, métriques, benchmark
complet) et `reports/benchmark_841.json`. La CI rejoue cet entraînement à chaque push.

## 7. Enjeux RGPD

Le prototype ne traite **aucune donnée personnelle** : données publiques et simulées,
identifiants de machines uniquement. Avec des données réelles, les points suivants
s'appliqueraient.

| Sujet | Analyse |
|---|---|
| Données concernées | Les mesures machine ne sont pas personnelles. Le deviennent : l'identité de l'opérateur, l'équipe en poste si elle permet d'identifier une personne, l'auteur d'une intervention de maintenance, les journaux de connexion aux dashboards. |
| Risque principal | Détourner la supervision des machines en surveillance de la performance individuelle des salariés. |
| Base légale et finalité | Intérêt légitime de l'employeur (maintenance, qualité). Finalité à limiter explicitement à la maintenance ; information des salariés et consultation du CSE. |
| Minimisation | Ne pas collecter l'identité de l'opérateur pour les modèles : ils n'en ont pas besoin. |
| Pseudonymisation | Remplacer les identifiants d'opérateurs et de techniciens par des codes, table de correspondance gardée séparément. Agréger par équipe plutôt que par personne. |
| Anonymisation | Pour l'entraînement et les jeux de test, supprimer toute colonne liée aux personnes. |
| Durée de conservation | À définir par finalité (par exemple : mesures détaillées 2 ans, agrégats plus longtemps). |
| Sécurité | Contrôle d'accès par rôle, chiffrement des échanges, journalisation des accès. |
| Rôle du DPO | Inscription au registre des traitements, avis sur la finalité, analyse d'impact (AIPD) si le traitement permet un suivi des salariés, point de contact pour l'exercice des droits. |
| Transferts | Sites en France et en Espagne : hébergement dans l'Union européenne. |
