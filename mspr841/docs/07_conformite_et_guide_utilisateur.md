# 07. Conformité au cahier des charges et guide utilisateur

> Compétence visée : *vérifier la conformité entre la solution développée et les
> fonctionnalités attendues, afin de rédiger la documentation orientée utilisateurs.*

## Partie A : Conformité

### A.1 Besoins exprimés dans le cahier des charges

| Exigence du cahier des charges | Réalisation | Statut | Preuve |
|---|---|---|---|
| Architecture intégrant sources IoT, SCADA/MES, historiques de maintenance | Architecture décrite ; sources remplacées par un jeu public et des données simulées | Conforme (prototype) | Document 02 |
| Prise en compte de la qualité des données (bruit, valeurs manquantes) | Défauts injectés en Bronze, traités en Silver | Conforme | Document 03 §1 |
| Cohérence temporelle des données | Sessions horodatées de 30 min ; validation temporelle des modèles | Conforme | Document 03 §3 |
| Centralisation des données | Couches Bronze / Silver / Gold | Conforme | `data/`, `notebooks/` |
| Jeux de données publics ou simulés, aucun réel | AI4I 2020 + simulation | Conforme | Document 03 §1 |
| Classification de l'état des machines (normal / à risque) | Modèle Usine B, probabilité de panne à 24 h | Conforme | Document 03 §5 |
| Prédiction d'un indicateur de dégradation (temps restant) | Modèle Usine A, durée de vie de l'outil | Conforme | Document 03 §4 |
| Étude d'arbres et d'ensembles d'arbres (Random Forest) | Random Forest et Gradient Boosting comparés dans les deux cas | Conforme | `reports/benchmark_841.json` |
| Modèles de régression plus simples en comparaison | Référence naïve, régression linéaire, Ridge, régression logistique | Conforme | idem |
| Détection de comportements atypiques | Règles de contrôle statistique (limites à 3 écarts-types) du moteur d'alertes ; pas de modèle dédié | Partiel | Document 04 §3.2 |
| Choix algorithmiques justifiés | Sélection par parcimonie, limites expliquées | Conforme | Document 03 |
| Conteneurisation | Deux images, Docker Compose | Conforme | Document 06 §1 |
| Architecture applicative d'exploitation des résultats | API + dashboards | Conforme | Documents 02, 04 |
| Mécanismes d'intégration IA ↔ application | API REST, fichiers, variables d'environnement | Conforme | Document 04 §2 |
| Paramétrage : règles de calcul, seuils, alertes, fréquences | `regles_metier.json`, `ALERT_RULES`, fréquences documentées | Conforme | Document 04 §3 |
| Langage ou formalisme de configuration | JSON de règles, règles déclaratives, contrat d'API | Conforme | Document 04 §3 |
| Interfaces et écrans métiers, usages | Onglet Prédictions IA, tableau des usages | Conforme | Document 04 §4–5 |
| Prompts d'IA générative fournis et analysés | Fournis | Conforme | Document 09 |
| Démarche de validation | Critères techniques et fonctionnels | Conforme | Document 05 §7 |
| Déploiement multi-sites, limites et prérequis | Plan en six phases | Conforme | Document 06 §4 |

### A.2 Livrables

| Livrable attendu | Statut | Emplacement |
|---|---|---|
| Code source versionné sur Git | Fait | https://github.com/Jason-Tch24/mspr |
| Jeux de données, données transformées, hypothèses | Fait | `data/`, `mspr841/ml/enrichir_usine_B.py`, `mspr841/ml/etendre_historique_B.py`, document 03 |
| Modèles, paramètres, métriques, interprétation | Fait | `mspr841/api/models/`, document 03 (dont le plafond théorique et l'enrichissement, §5) |
| Configuration de conteneurisation et instructions | Fait | `docker-compose.yml`, README, document 06 |
| Chaîne d'intégration continue | Fait | `.github/workflows/ci.yml` |
| Description de la solution applicative | Fait | Document 04 |
| Schéma d'architecture | Fait | Document 02 |
| Choix techniques, modèles étudiés, limites | Fait | Documents 02, 03 |
| Principes de déploiement et d'exploitation | Fait | Document 06 |
| Enjeux RGPD | Fait | Document 03 §7 |
| Guide d'entretien et synthèse des besoins | Fait | Document 01 |
| Compte-rendu des échanges avec le client | À corriger : version simulée, à corriger par l'équipe avec les échanges réels | Document 01 §6 |
| Guide utilisateur métier | Fait | Partie B ci-dessous |
| Conduite du changement | Fait | Document 08 |
| Validation globale et projection de mise en œuvre | Fait | Documents 05, 06 |
| Support de soutenance | Fait : 10 diapositives avec notes d'orateur | https://claude.ai/artifact/UAK3UVWLGvtSg9tYeo7qVH (lien privé, à partager ou exporter) |

### A.3 Écarts et plan d'amélioration

| Écart | Conséquence | Action proposée | Priorité |
|---|---|---|---|
| Prédictions non historisées (besoin BF9) | Impossible de mesurer après coup la justesse des alertes | Enregistrer chaque prédiction et la décision prise | Haute |
| Pas de modèle de détection d'anomalies | Les comportements inédits ne sont vus que par les règles de seuil | Ajouter une forêt d'isolement sur les mesures capteurs | Moyenne |
| Pas de notification (besoin BF10) | Il faut consulter l'écran pour voir une alerte | Courriel ou notification mobile au niveau « Critique » | Moyenne |
| Pas d'authentification | Acceptable en démonstration, pas en production | Authentification unique de l'entreprise | Haute avant pilote |
| Usine C sans modèle | Un des trois sites simulés n'a pas d'IA | Modèle d'instabilité du process | Basse |
| Données simulées | Performance réelle inconnue | Phase d'observation sur site pilote | Haute |

---

## Partie B : Guide utilisateur métier

*Destiné aux responsables maintenance et production. À imprimer sur deux pages.*

### À quoi sert l'outil

L'outil vous aide à intervenir avant la panne. Il répond à deux questions :

- Usine A : *Dans combien de temps faut-il changer l'outil de coupe ?*
- Usine B : *Cette machine risque-t-elle une panne thermique dans les 24 heures ?*

Il ne pilote pas les machines et n'arrête rien tout seul : c'est vous qui décidez.

### Y accéder

Ouvrez le dashboard de votre usine, puis l'onglet Prédictions IA :
Usine A `http://<serveur>:8051` · Usine B `http://<serveur>:8052` · Groupe `http://<serveur>:8050`.

### Lire l'écran : Usine A (usure de l'outil)

| Ce que vous voyez | Ce que cela veut dire | Que faire |
|---|---|---|
| OK : plus de 20 sessions restantes (plus de 10 h) | L'outil est en bon état | Rien de particulier |
| WARNING : entre 10 et 20 sessions (5 à 10 h) | Le remplacement approche | Préparer l'outil de rechange ; viser le prochain changement de série |
| CRITICAL : 10 sessions ou moins (5 h ou moins) | Remplacement imminent | Planifier l'intervention maintenant |

Une session dure 30 minutes. La durée est aussi affichée en heures.
Marge d'erreur constatée : environ une session, soit 30 minutes.

### Lire l'écran : Usine B (risque thermique)

| Ce que vous voyez | Ce que cela veut dire | Que faire |
|---|---|---|
| Normal : probabilité inférieure à 45 % | La machine évacue correctement sa chaleur | Surveillance habituelle |
| À risque : de 45 à 65 % | Le refroidissement se dégrade | Vérifier le circuit de refroidissement pendant le poste |
| Critique : 65 % ou plus | Forte probabilité de panne sous 24 h | Contrôler le refroidissement sans attendre ; envisager un arrêt planifié |

Le chiffre affiché est la probabilité qu'au moins une panne thermique survienne dans les
24 heures. La mention « *n sessions d'historique analysées* » indique sur combien de
mesures passées l'estimation s'appuie : plus il y en a (jusqu'à 47), plus elle est fiable.

> Repère : le risque thermique augmente quand l'écart de température entre le process
> et l'air ambiant diminue (valeur normale : environ 11,5 K).

### Comment interpréter les résultats

- Un niveau n'est pas une certitude. Sur les données d'essai, une panne est survenue
  dans les 24 h dans environ 7 cas sur 10 au niveau « Critique », 6 sur 10 au niveau
  « À risque » et 3 sur 10 au niveau « Normal ».
- L'outil classe les priorités : il vous dit où regarder en premier, pas où il est
  inutile de regarder.
- Croisez avec les autres onglets : Maintenance (tendance thermique, usure) et Alertes
  (seuils franchis en ce moment).
- Regardez l'évolution plutôt qu'une valeur isolée : un niveau qui monte sur plusieurs
  heures est un signal plus sûr qu'un pic.

### Limites et conditions d'usage

- L'outil ne remplace pas la maintenance préventive ni votre connaissance des machines.
- Il a été mis au point sur des données simulées : ses seuils devront être réajustés
  avec vos retours.
- Il ne voit que deux types de défaillance : l'usure de l'outil (usine A) et la panne
  thermique (usine B). Il ne détecte pas les casses brutales ni les défauts électriques.
- Une prédiction faite avec peu d'historique (après un redémarrage) est moins fiable.
- En cas de doute sur une machine, la sécurité prime sur l'indication de l'outil.

### En cas de problème

| Situation | Explication | Que faire |
|---|---|---|
| « API indisponible » dans l'onglet IA | Le service de prédiction est arrêté ; les autres onglets fonctionnent | Prévenir le support informatique ; continuer avec les onglets habituels |
| Trop d'alertes, ou pas assez | Les seuils ne conviennent pas à votre atelier | Demander un réglage au référent IA du site |
| Une alerte ne correspond pas à la réalité | Erreur du modèle ou capteur défaillant | Le signaler au référent IA : ces retours servent à améliorer l'outil |

Contacts : référent IA du site · support informatique · responsable maintenance.
