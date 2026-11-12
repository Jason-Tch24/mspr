# 01 — Collecte des besoins métiers

> Compétence visée : *collecter les besoins métiers des utilisateurs en menant des interviews
> pour comprendre leurs activités et leurs contraintes, afin d'étudier les opportunités et la
> faisabilité d'une solution applicative.*

## 1. Cadre de la collecte

L'équipe n'a aucun contact direct avec MECHA : le cahier des charges est la seule expression
officielle du besoin et l'encadrant pédagogique joue le rôle du client. Les entretiens
ci-dessous sont donc **simulés**, comme le sujet l'autorise : les réponses sont déduites du
cahier des charges TPRE841, du cas d'usage « maintenance prédictive des centres d'usinage »
et des constats du bloc 3 (TPRE831). Elles sont à confronter aux retours de l'encadrant
(section 6).

## 2. Méthode

| Étape | Ce qui est fait | Production |
|---|---|---|
| 1. Cartographie des acteurs | Identifier qui utilise, qui décide, qui exploite | Tableau des profils (§3) |
| 2. Entretiens semi-directifs | 45 min par profil, questionnaire commun + questions propres au métier | Notes d'entretien |
| 3. Retranscription | Chaque réponse est ramenée à une ligne « verbatim → besoin → critère d'acceptation » | Tableau de retranscription (§5) |
| 4. Priorisation | Méthode MoSCoW avec le commanditaire | Besoins priorisés (§5) |
| 5. Validation | Relecture par le client (encadrant) | Compte-rendu (§6) |

Le format **tableau** est retenu pour la retranscription : il oblige à reformuler chaque
propos en besoin vérifiable et il sert ensuite directement de base à la matrice de
conformité (document 07).

## 3. Acteurs interrogés

| Profil | Rôle vis-à-vis de la solution | Ce qu'il en attend |
|---|---|---|
| Technicien de maintenance | Utilisateur quotidien | Savoir sur quelle machine intervenir, et quand |
| Responsable maintenance | Utilisateur et prescripteur | Planifier les interventions, justifier les arrêts |
| Responsable de production | Utilisateur | Ajuster le planning sans arrêt imprévu |
| Direction industrielle | Commanditaire | Suivre disponibilité, rebuts et coûts sur les sites |
| Direction qualité | Partie prenante | Traçabilité, réaction rapide aux dérives |
| DSI / équipe data | Exploitant | Intégration au SI, sécurité, maintenabilité |

## 4. Guide d'entretien type

**Introduction (5 min)** — objet du projet, durée, usage des réponses, accord pour la prise de notes.

**A. Activité et situation actuelle**
1. Décrivez une journée type : quelles décisions prenez-vous sur les machines ?
2. Comment apprenez-vous aujourd'hui qu'une machine va mal ? Avec quel délai ?
3. Racontez la dernière panne non planifiée : que s'est-il passé, qu'a-t-elle coûté ?
4. Quels outils consultez-vous (SCADA, MES, tableurs, GMAO) et à quelle fréquence ?

**B. Besoins fonctionnels**
5. Quelle information vous manque pour anticiper une intervention ?
6. Quel délai d'anticipation vous est utile : 1 heure, un poste, 24 heures, une semaine ?
7. Préférez-vous un score, un niveau (vert / orange / rouge) ou une durée restante ?
8. Que doit-il se passer quand un seuil est franchi (affichage, notification, ordre de travail) ?
9. Sur quel support consultez-vous l'information (poste fixe, écran d'atelier, mobile) ?

**C. Contraintes**
10. Quelles alertes ignorez-vous aujourd'hui, et pourquoi ?
11. Combien de fausses alertes par semaine seriez-vous prêt à accepter ?
12. Quelles contraintes de sécurité, de réseau ou de disponibilité s'imposent dans l'atelier ?
13. Qui doit pouvoir modifier les seuils ? Faut-il une validation ?

**D. Critères de succès**
14. Dans six mois, à quoi verrez-vous que l'outil vous est utile ?
15. Qu'est-ce qui vous ferait cesser de l'utiliser ?

**Conclusion (5 min)** — reformulation des trois points clés, suite donnée.

## 5. Retranscription et synthèse des besoins

### Besoins fonctionnels

| Id | Verbatim (simulé) | Besoin reformulé | Priorité | Critère d'acceptation |
|---|---|---|---|---|
| BF1 | « Je veux savoir quand changer l'outil avant qu'il casse. » — technicien, usine A | Estimer le temps restant avant remplacement de l'outil | Must | Une durée en sessions et en heures est affichée pour la machine |
| BF2 | « Dites-moi si la machine est normale ou à risque, pas un graphique à interpréter. » — responsable maintenance, usine B | Classer l'état de la machine : normal / à risque | Must | Un niveau et une probabilité sont affichés, avec un message d'action |
| BF3 | « Une alerte doit me dire quoi faire. » — technicien | Associer à chaque niveau un message d'action clair | Must | Chaque réponse de l'IA contient une phrase d'interprétation |
| BF4 | « Les seuils ne sont pas les mêmes d'un site à l'autre. » — direction industrielle | Rendre les seuils d'alerte paramétrables sans développement | Must | Seuils modifiables dans un fichier de configuration |
| BF5 | « Je veux tout voir sur le même écran que mes KPI. » — responsable production | Intégrer les résultats IA aux dashboards existants | Must | Onglet IA dans les dashboards des usines A et B |
| BF6 | « Il faut pouvoir montrer ce qui se passe en cas de panne. » — direction industrielle | Simuler une dégradation pour démontrer et former | Should | Boutons d'injection de panne dans l'onglet IA |
| BF7 | « D'autres applications voudront ces scores. » — DSI | Exposer les prédictions par un service réutilisable | Should | API REST documentée |
| BF8 | « Je dois pouvoir expliquer d'où vient le chiffre. » — direction qualité | Afficher le modèle utilisé et sa performance | Should | Libellé du modèle et métriques visibles ; endpoint `/models` |
| BF9 | « Garder la trace des prédictions et des décisions. » — direction qualité | Historiser prédictions et actions | Could | Non réalisé dans le prototype (voir document 07) |
| BF10 | « Recevoir l'alerte sur mon téléphone. » — technicien | Notification mobile | Won't (prototype) | Hors périmètre, prévu en industrialisation |

### Contraintes métier et techniques

| Id | Contrainte | Conséquence sur la solution |
|---|---|---|
| C1 | Aucune donnée réelle utilisable (confidentialité) | Jeu public AI4I 2020 adapté et données simulées |
| C2 | Cinq usines au niveau d'équipement hétérogène | Solution conteneurisée, déployable site par site |
| C3 | La production ne doit pas dépendre de l'IA | Si l'API est indisponible, les dashboards restent utilisables |
| C4 | Données capteurs bruitées, parfois manquantes | Champs optionnels remplacés par des valeurs médianes ; mode dégradé signalé |
| C5 | Les fausses alertes font abandonner l'outil | Trois niveaux, seuils réglables, taux de panne observé par niveau documenté |
| C6 | Résultats lisibles par des non-spécialistes | Niveau + phrase d'action plutôt qu'un score brut |
| C7 | Intégration au SI existant (SCADA, MES) | Échanges en JSON sur HTTP, contrat d'API explicite |
| C8 | Sécurité des systèmes industriels | Conteneurs sans privilèges, réseau interne ; authentification à ajouter en production |

### Opportunité et faisabilité

| Question | Réponse |
|---|---|
| Le besoin est-il réel ? | Oui : arrêts non planifiés et rebuts sont les deux enjeux cités par la direction industrielle. |
| Les données existent-elles ? | Capteurs IoT, SCADA et MES sont déployés ; l'historique de pannes reste à consolider. |
| La technologie est-elle mûre ? | Oui : modèles classiques (régression, forêts), API REST, conteneurs. |
| Quel est le principal risque ? | La qualité de l'historique réel, qui conditionne la performance des modèles. |

## 6. Compte-rendu des échanges avec le client (encadrant)

> **Échanges simulés — à corriger par l'équipe.** Les trois points ci-dessous sont une
> proposition plausible, rédigée à partir du cahier des charges et de l'avancement réel du
> projet. Avant la soutenance : remplacer les dates, les noms et les réponses par ce qui a
> été réellement dit, et supprimer ce bandeau. Ne pas présenter ce texte au jury comme un
> compte-rendu réel sans l'avoir corrigé.

**Participants** : l'équipe projet (5 personnes) ; l'encadrant pédagogique, dans le rôle du
client (Direction industrielle de MECHA). Format : points de 20 à 30 minutes.

### Point 1 — Cadrage du besoin · [date à renseigner]

| Question posée par l'équipe | Réponse du client | Décision | Impact sur le projet |
|---|---|---|---|
| Quel est le cas d'usage prioritaire : usure de l'outil, panne thermique, ou les deux ? | Les arrêts non planifiés sont la priorité. Les deux cas sont pertinents s'ils restent simples à expliquer. | Traiter les deux, un par usine pilote | Usine A : durée de vie de l'outil. Usine B : risque thermique. |
| Quel délai d'anticipation attend la maintenance ? | Un poste à une journée : assez pour préparer l'intervention sans arrêter la ligne. | Horizon de 24 h pour le risque thermique | Cible du modèle B fixée à « panne dans les 24 h » |
| Peut-on utiliser des données réelles ? | Non, pour des raisons de confidentialité. Données publiques ou simulées uniquement. | Jeu public AI4I 2020 + simulation | Hypothèses de simulation à documenter (document 03) |
| Qui utilisera l'outil au quotidien ? | Les techniciens et le responsable maintenance, pas des spécialistes des données. | Résultat sous forme de niveau et de consigne | Trois niveaux d'alerte et une phrase d'action plutôt qu'un score |

### Point 2 — Avancement et choix techniques · [date à renseigner]

| Question posée par l'équipe | Réponse du client | Décision | Impact sur le projet |
|---|---|---|---|
| Le modèle le plus simple suffit-il, ou attendez-vous des forêts aléatoires ? | Le sujet demande de les étudier et de justifier le choix, pas de les imposer. | Comparer, puis retenir le plus simple à performance égale | Règle de parcimonie (document 03 §3) |
| Les seuils d'alerte doivent-ils être modifiables par le métier ? | Oui, sans redéveloppement. Trop de fausses alertes et l'outil sera abandonné. | Seuils dans un fichier de configuration | `regles_metier.json`, relu par l'API |
| Que doit-il se passer si le service d'IA est indisponible ? | La supervision doit continuer : la production ne s'arrête pas pour un outil d'aide. | L'IA est un service séparé | Architecture en micro-service, message « API indisponible » |
| Le premier modèle thermique donnait des résultats incohérents. Pouvons-nous reformuler la cible ? | Oui, si la reformulation est expliquée et vérifiable. | Passage de trois classes à « normal / à risque » | Document 03 §5, anomalie tracée au plan de test |

### Point 3 — Validation avant soutenance · [date à renseigner]

| Question posée par l'équipe | Réponse du client | Décision | Impact sur le projet |
|---|---|---|---|
| Une démonstration sur données simulées suffit-elle ? | Oui, à condition de dire clairement ce qu'elle prouve et ce qu'elle ne prouve pas. | Réserves écrites dans le dossier | Document 05 §7, section « Limites » du support |
| Les scores du modèle thermique plafonnaient. Peut-on enrichir la simulation ? | Oui, le sujet l'autorise, si les hypothèses sont réalistes et documentées. | Ajout de signes avant-coureurs avant les pannes | `enrichir_usine_B.py`, document 03 §1 et §5 |
| Quel niveau de détail attendez-vous sur le déploiement multi-sites ? | Un plan progressif, avec les prérequis et les risques, pas un planning au jour près. | Déploiement en six phases, site pilote d'abord | Document 06 §4 |
| Qu'attendez-vous de la soutenance ? | Une démonstration qui fonctionne, et que chacun sache expliquer sa partie. | Répétition sur la machine de soutenance | Scénario de démonstration (document 05 §5) |

### Synthèse des décisions

1. Deux cas d'usage, un par usine pilote ; horizon de 24 h pour le risque thermique.
2. Données publiques et simulées uniquement, hypothèses documentées.
3. Modèle le plus simple à performance égale ; seuils réglables par le métier.
4. L'IA est un service séparé : la supervision fonctionne sans elle.
5. Les limites de la validation sur données simulées sont dites explicitement.
