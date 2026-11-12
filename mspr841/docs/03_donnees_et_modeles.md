# 03. Données et modèles

## 1. Origine des données

| Couche | Fichier | Contenu | Origine |
|---|---|---|---|
| Source | `data/source/ai4i2020.csv` | 10 000 lignes, 14 colonnes | Jeu public AI4I 2020 Predictive Maintenance (UCI) |
| Bronze | `data/bronze/ai4i_raw.csv`, `ai4i_raw_dirty.csv` | Copie brute + version dégradée volontairement | Script `notebooks/00_bronze.ipynb` |
| Silver | `data/silver/ai4i_clean.parquet` | Données nettoyées et contrôlées | `notebooks/01_silver.ipynb` |
| Gold étendu | `data/gold/usine_B_historique.parquet` | 50 209 sessions du 01/01/2024 au 12/11/2026, pour l'entraînement du modèle de l'usine B | `mspr841/ml/etendre_historique_B.py` |
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
| A (Lyon) | Usure progressive de l'outil | L'usure augmente à chaque session d'un incrément aléatoire dépendant du type de pièce ; l'outil est remplacé à la limite ; le rebut augmente avec l'usure. |
| B (Bordeaux) | Pannes thermiques groupées, précédées d'une dérive | Delta thermique = 11,5 K − 2,5 × sinus (période 45 jours) + bruit (σ = 0,5 K). Pannes tirées selon un processus de Poisson dont le taux suit la même sinusoïde et est multiplié par 3 sous 8,6 K. Signes avant-coureurs ajoutés ensuite (voir ci-dessous). |
| C (Toulouse) | Instabilité du process | Non utilisée par les modèles du bloc 4. |

### Enrichissement de l'usine B : signes avant-coureurs (`mspr841/ml/enrichir_usine_B.py`)

Le fichier d'origine est conservé (`data/gold/usine_B_base.parquet`). Le script en repart
toujours, avec une graine fixée : le relancer redonne le même résultat. Le bilan est tracé
dans `data/gold/enrichissement_usine_B.json`.

| Hypothèse | Règle | Volume |
|---|---|---|
| H1 : dégradation avant la panne | 80 % des pannes thermiques sont précédées d'une baisse progressive du delta de 1,2 à 2,5 K, sur les 12 à 36 h qui précèdent | 93 pannes sur 111 |
| H1 bis : casse brutale | Les 20 % restants surviennent sans signe | 18 pannes |
| H2 : retour à la normale | Après la panne, l'intervention rétablit le delta en 3 h | - |
| H3 : fausses dérives | Une dérive sans panne pour quatre pannes : le delta baisse puis revient seul | 28 dérives |
| H4 : cohérence | Température process, taux de rebut, stabilité, qualité, TRS et limites de contrôle recalculés avec les formules du notebook Gold | 57 % des sessions touchées |

Les pannes (dates, nombre, durées) ne sont pas modifiées : seules les mesures qui les
précèdent changent. Le delta moyen passe de 11,49 K à 11,01 K.

### Extension de l'historique de l'usine B (`mspr841/ml/etendre_historique_B.py`)

Six mois d'historique, c'est 111 pannes thermiques et quatre cycles thermiques : trop peu
pour départager des modèles. Le script prolonge la simulation de l'usine B du 29/06/2024 au
12/11/2026, avec exactement les mêmes règles (loi d'origine, puis signes avant-coureurs H1
à H3). Le bilan est tracé dans `data/gold/extension_usine_B.json`.

| | Six mois du Gold | Extension simulée | Total |
|---|---|---|---|
| Sessions de 30 min | 8 640 | 41 569 | 50 209 |
| Pannes thermiques | 111 | 542 | 653 |
| Taux de panne par session | 1,28 % | 1,30 % | 1,30 % |
| Delta thermique moyen | 11,01 K | 10,98 K | 10,99 K |

Les six premiers mois ne sont pas modifiés : ce sont ceux que les tableaux de bord
rejouent. Le fichier étendu (`data/gold/usine_B_historique.parquet`) ne sert qu'à
l'entraînement. La date de fin est fixée dans le script, pour que le résultat soit
reproductible. L'usine A n'a pas été étendue : son modèle est déjà au plancher d'erreur
(§5), des données supplémentaires n'y changeraient rien.

### Limites connues des données

- Volume : 6 mois et 115 remplacements d'outil pour l'usine A ; 34 mois et 653 pannes thermiques pour l'usine B après extension, dont 28 mois entièrement simulés par nos soins.
- Simplifications : une seule cause dominante par usine ; pas d'effet de l'opérateur, de la matière ou de la saison.
- Biais : l'usure est quasi linéaire ; les pannes thermiques sont en partie aléatoires et leurs signes avant-coureurs sont une hypothèse de simulation. Les scores ci-dessous reflètent ces règles, pas le comportement de machines réelles.
- Session : les données sont à la maille de 30 minutes ; aucun signal haute fréquence (vibrations).

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
| `temp_process_delta` | décimal | K, ≈ 7,5 à 15,5 | Écart process − air. Un delta bas signale une mauvaise dissipation de chaleur. |
| `delta_ma` (usine B) | décimal | K | Moyenne mobile du delta sur 100 sessions |
| `vitesse_rotation_rpm` | entier | tr/min, ≈ 1 250 à 1 850 | Vitesse de broche |
| `couple_nm` | décimal | N·m, 20 à 70 | Couple de coupe |
| `usure_outil_min` | décimal | minutes | Temps d'usage cumulé de l'outil |
| `usure_cumulee_pct` | décimal | %, 0 à 90 | Usure rapportée à la durée de vie de l'outil |
| `remplacement_outil` | 0/1 | - | Outil remplacé pendant la session |
| `panne_machine` | 0/1 | - | Une panne, toutes causes |
| `panne_thermique`, `panne_usure_outil`, `panne_puissance`, `panne_surcharge`, `panne_aleatoire` | 0/1 | - | Cause de la panne |
| `type_panne` | texte | Aucune, Thermique, Usure outil… | Libellé de la cause |
| `duree_arret_min` | décimal | minutes | Durée de l'arrêt |
| `nb_pannes_7j` | entier | - | Pannes sur les 7 jours glissants |
| `intervention_maintenance` | 0/1 | - | Intervention réalisée |
| `temps_cycle_min` | décimal | minutes | Temps de cycle mesuré |
| `derive_cycle_pct` | décimal | % | Écart au temps de cycle nominal |
| `pieces_produites`, `pieces_rebutees` | entier | pièces | Production de la session |
| `taux_rebut` | décimal | 0 à 1 | Part de pièces rebutées |
| `indice_stabilite_process` | décimal | 0 à 1 | 1 = process stable |
| `consommation_kwh` | décimal | kWh | Énergie de la session |
| `rupture_appro` | 0/1 | - | Rupture d'approvisionnement |
| `disponibilite`, `performance`, `qualite` | décimal | 0 à 1 | Composantes du TRS |
| `TRS` | décimal | 0 à 1 | Taux de rendement synthétique |
| `TRS_7j` | décimal | 0 à 1 | TRS moyen sur 7 jours |

## 3. Démarche de modélisation

La même démarche est appliquée aux deux cas (`mspr841/ml/train_models.py`).

1. Cible construite uniquement à partir du futur de la série.
2. Variables définies une seule fois dans `features.py`, utilisées à l'entraînement et par l'API.
3. Comparaison de plusieurs modèles, dont des références simples, comme le demande le sujet.
4. Validation temporelle « walk-forward » (`TimeSeriesSplit`, 5 plis) : on entraîne toujours sur le passé et on teste sur le futur. Un découpage aléatoire laisserait le modèle « voir » le futur.
5. Sélection par parcimonie : on retient le modèle le plus simple dont la performance est à moins de 1 % du meilleur.
6. Ré-entraînement sur tout l'historique, export du modèle et de ses métadonnées.

## 4. Usine A : durée de vie résiduelle de l'outil (régression)

- Cible : nombre de sessions avant le prochain remplacement d'outil.
- Variables : 11 mesures instantanées (usure cumulée, TRS, temps de cycle, dérive, disponibilité, performance, qualité, consommation, vitesse, couple, taux de rebut).
- Volume : 8 464 sessions.

| Modèle | MAE (sessions) | RMSE | R² |
|---|---|---|---|
| Moyenne (référence naïve) | 18,39 | 21,25 | 0,000 |
| Linéaire sur l'usure seule (retenu) | 1,05 | 1,35 | 0,996 |
| Ridge (11 variables) | 1,05 | 1,35 | 0,996 |
| Random Forest | 1,09 | 1,41 | 0,996 |
| Gradient Boosting | 1,08 | 1,38 | 0,996 |
| Extra Trees | 1,08 | 1,39 | 0,996 |
| Gradient Boosting par histogrammes | 1,08 | 1,38 | 0,996 |
| k plus proches voisins | 3,01 | 3,96 | 0,965 |
| Réseau de neurones (MLP) | 1,23 | 1,58 | 0,994 |

Interprétation. L'erreur moyenne est d'environ une session, soit 30 minutes. Les modèles
complexes n'apportent rien : la durée de vie se déduit presque entièrement de l'usure
cumulée. Le modèle retenu est donc le plus simple, et le plus facile à expliquer à un
technicien (« chaque point d'usure consomme une durée connue »).

Ce qui n'a pas marché. Les k plus proches voisins font trois fois plus d'erreur : sur onze
variables mises à la même échelle, dix ne portent aucune information sur la durée restante
et brouillent la notion de voisinage. Le réseau de neurones est moins bon et moins stable
que la droite : il doit apprendre une relation linéaire qu'on peut écrire directement.

Limite. Ce R² très élevé vient de la simulation, où l'usure progresse presque
linéairement. Sur des machines réelles (usure non linéaire, casse brutale, changement de
matière), il faudra s'attendre à une erreur nettement plus forte et les modèles non
linéaires redeviendront pertinents.

## 5. Usine B : risque de panne thermique à 24 h (classification)

- Cible : « à risque » = au moins une panne thermique dans les 48 sessions suivantes (24 h). La session courante est exclue : on prédit, on ne constate pas.
- Variables : 5 indicateurs du régime thermique : delta courant, moyenne 6 h, moyenne 24 h, minimum 6 h, tendance (moyenne 6 h − moyenne 24 h).
- Volume : 50 161 sessions sur 34 mois (historique étendu, §1), dont 44,5 % « à risque ».
- Validation : 5 plis temporels séparés par un intervalle de 48 sessions, pour qu'aucune session d'entraînement ne recouvre le futur du pli de test.

| Modèle | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|
| Fréquence de base (référence naïve) | 0,500 | 0,445 | 0,247 |
| Régression logistique sur le delta instantané | 0,791 | 0,758 | 0,185 |
| Régression logistique à 5 variables (retenu) | 0,803 | 0,765 | 0,179 |
| Random Forest | 0,782 | 0,756 | 0,190 |
| Gradient Boosting | 0,797 | 0,771 | 0,182 |
| Extra Trees | 0,802 | 0,776 | 0,180 |
| Gradient Boosting par histogrammes | 0,799 | 0,775 | 0,181 |
| k plus proches voisins | 0,792 | 0,763 | 0,184 |
| Réseau de neurones (MLP) | 0,806 | 0,778 | 0,178 |

Interprétation. Les neuf modèles se tiennent dans un mouchoir : de 0,78 à 0,81 de ROC-AUC.
Le réseau de neurones arrive en tête de 0,003, soit moins que l'écart observé d'un pli à
l'autre (0,004 à 0,014 selon les modèles). La règle de parcimonie retient donc la régression
logistique à cinq variables : même performance à 1 % près, cinq coefficients lisibles, et
aucun réglage à entretenir. Le modèle se comporte comme attendu physiquement : la
probabilité de panne augmente quand le delta thermique baisse (0,04 à 15,5 K ; 0,31 au
nominal de 11,5 K ; 0,82 à 7,6 K, en régime établi). Il réagit aussi à la tendance : à
9,5 K, la probabilité est de 0,60 en régime stable et de 0,81 si ce niveau vient d'être
atteint après une dérive de 2 K en 12 h.

Ce qui n'a pas marché.

- Le Random Forest reste le moins bon des modèles complets (0,782), même avec six fois
  plus de données. Les cinq variables sont très corrélées entre elles (ce sont cinq
  lectures du même signal) : les arbres les découpent en paliers là où la relation est
  régulière.
- Le delta instantané seul plafonne à 0,791 : il ignore la tendance, qui est précisément
  ce que les signes avant-coureurs apportent.
- Les modèles plus souples (boosting, Extra Trees, réseau de neurones) n'ajoutent rien de
  mesurable à la régression logistique. Le signal disponible est simple : un niveau et une
  tendance. Il n'y a pas d'interaction cachée à découvrir.
- Sur six mois seulement, les mêmes ensembles d'arbres étaient nettement derrière (0,77 à
  0,79 contre 0,81) et variaient de 0,03 à 0,05 d'un pli à l'autre. L'extension de
  l'historique a ramené cette dispersion sous 0,01 : le classement est maintenant fiable.

### Plafond théorique et enrichissement des données

Les données étant simulées, la loi qui génère les pannes est connue. On peut donc calculer
la performance du meilleur prédicteur possible, celui qui connaîtrait cette loi
(`mspr841/ml/plafond_theorique.py`, résultat dans `reports/plafond_841.json`).

Étape 1 : constat sur la simulation d'origine. Le premier modèle obtenait une ROC-AUC
de 0,738 ; le prédicteur parfait plafonnait à 0,746. Le modèle captait donc déjà 97 % du
signal prévisible, et aucun changement d'algorithme ne pouvait l'améliorer : l'instant d'une
panne était tiré au hasard, seul son *taux* dépendait du régime thermique. Variantes testées
sans gain : moyennes sur 48 h à 7 jours, pente du delta, splines, gradient boosting par
histogrammes.

Étape 2 : enrichissement des données. Pour progresser, il fallait changer les données
et non le modèle. Sur une machine réelle, une panne thermique est le plus souvent précédée
d'une dégradation progressive. Le script `mspr841/ml/enrichir_usine_B.py` ajoute cette
hypothèse (détail au §1) sans toucher aux pannes elles-mêmes.

Étape 3 : extension de l'historique. De 6 à 34 mois, pour comparer neuf modèles sur un
volume suffisant (détail au §1).

| Usine B | 1. Simulation d'origine, 6 mois | 2. Avec signes avant-coureurs, 6 mois | 3. Avec signes avant-coureurs, 34 mois |
|---|---|---|---|
| ROC-AUC | 0,738 | 0,813 | 0,803 |
| Écart-type entre plis | 0,036 | 0,030 | 0,007 |
| PR-AUC | 0,609 | 0,740 | 0,765 |
| Brier (plus bas = mieux) | 0,211 | 0,178 | 0,179 |
| Précision de l'alerte | 63 % | 70 % | 70 % |
| Rappel de l'alerte | 57 % | 62 % | 70 % |
| Plafond du régime seul (ROC-AUC) | 0,746 | 0,746 | 0,758 |

Le modèle dépasse le plafond du régime seul : l'écart (+0,05 de ROC-AUC sur 34 mois)
mesure ce qu'apporte la dérive du delta avant la panne. L'algorithme et les cinq variables
sont inchangés ; c'est la variable de tendance qui porte le gain.

Entre les étapes 2 et 3, la ROC-AUC passe de 0,813 à 0,803. Ce n'est pas une dégradation
du modèle : la mesure sur six mois reposait sur 111 pannes et variait de 0,03 d'un pli à
l'autre. Celle sur 34 mois repose sur 653 pannes et ne varie plus que de 0,007. C'est le
chiffre de l'étape 3 qu'il faut retenir. Le rappel de l'alerte, lui, progresse de 62 à 70 %.

Usine A. L'erreur moyenne du modèle (1,05 session) est au plancher : le prédicteur
parfait, estimé sur 20 000 vies d'outil simulées, fait 1,10. Le nombre de sessions restantes
dépend des pièces qui seront usinées, tirées au hasard. Le modèle A n'a donc pas été modifié.

Limite à dire au jury. Le gain du modèle B vient d'une hypothèse de simulation, pas
d'une mesure sur des machines. Si les pannes réelles de MECHA ne sont pas précédées d'une
dérive, le modèle retombera au niveau du régime seul. C'est la première chose à vérifier
lors d'un pilote sur site.

### Des probabilités aux niveaux d'alerte

Les seuils sont du paramétrage applicatif (`regles_metier.json`), pas une propriété du
modèle. Lecture sur les prédictions de validation :

| Niveau | Seuil | Part des sessions | Taux de panne réellement observé dans les 24 h |
|---|---|---|---|
| Normal | p < 0,45 | 55 % | 24 % |
| À risque | 0,45 ≤ p < 0,65 | 19 % | 53 % |
| Critique | p ≥ 0,65 | 26 % | 81 % |

À partir du niveau « À risque », l'alerte détecte 70 % des périodes suivies d'une panne
(rappel) et se vérifie 70 % du temps (précision).

Limite. Le modèle estime un niveau de risque, pas l'instant d'une panne : une panne
sur cinq survient sans signe avant-coureur, et les autres ne sont annoncées que par une
dérive progressive. Même au niveau « Normal », 24 % des périodes de 24 h contiennent une panne. Le
modèle sert donc à prioriser les contrôles, pas à remplacer la maintenance préventive.
Un recalibrage sur données terrain est indispensable.

### Ce qui a été corrigé par rapport au premier PoC

Le premier modèle (3 classes « Normal / Risque / Critique », exactitude équilibrée de 0,45)
classait un delta nominal en « Critique » et un delta extrême en « Normal ». Trois causes :

1. la classe « Critique » (panne dans les 3 sessions) n'était pas prévisible, les pannes étant aléatoires à cet horizon ;
2. l'API ne recevait pas les variables d'historique et les remplaçait par des constantes, jamais vues à l'entraînement ;
3. le scénario de démonstration injectait un delta de 20 K, alors que le risque apparaît quand le delta baisse.

La cible a été reformulée en « normal / à risque » comme le demande le cahier des charges,
l'historique est maintenant transmis par le dashboard, et les features sont partagées.

## 6. Reproduire les résultats

```bash
pip install -r mspr841/ml/requirements.txt
python mspr841/ml/enrichir_usine_B.py     # signes avant-coureurs (usine B)
python mspr841/ml/etendre_historique_B.py # historique étendu jusqu'au 12/11/2026
python mspr841/ml/train_models.py
python mspr841/ml/plafond_theorique.py
```

Sorties : `mspr841/api/models/*.joblib`, `*_meta.json` (paramètres, métriques, benchmark
complet) et `reports/benchmark_841.json`. La CI rejoue cet entraînement à chaque push.

## 7. Enjeux RGPD

Le prototype ne traite aucune donnée personnelle : données publiques et simulées,
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
