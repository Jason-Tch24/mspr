# 10. Prompts de reproduction des livrables

> Statut de ce document. Ces prompts ont été rédigés après coup. Ils décrivent la
> demande qu'il faudrait adresser à un assistant d'IA générative pour obtenir chaque
> livrable du dossier. Ce ne sont pas les prompts réellement saisis pendant le projet :
> ceux-là sont reproduits au document 09 §2. Ne pas présenter ce document comme l'historique
> des échanges avec l'IA.

Chaque prompt suppose que l'assistant a accès au dépôt du projet et au sujet TPRE841.
Trois consignes sont communes à tous :

- s'appuyer sur le code et les fichiers réels, citer les chemins, ne rien inventer ;
- relire chaque chiffre dans le fichier qui le produit (`reports/benchmark_841.json`, etc.) ;
- signaler ce qui est simulé, supposé ou non fait, au lieu de le masquer.

## Livrables techniques

#### Code source et dépôt Git

> Fais l'audit du dépôt au regard du sujet TPRE841 et de la grille du bloc 4. Liste ce qui
> manque ou ne fonctionne pas, propose un ordre de travail, puis réalise-le par petites
> étapes : une branche, des commits lisibles, une pull request par lot.

#### Jeux de données et hypothèses de simulation

> Décris l'origine des données du projet, couche par couche (source, Bronze, Silver, Gold).
> Rédige le dictionnaire de données de la couche Gold : colonne, type, unité, signification.
> Liste les hypothèses de simulation en relisant les notebooks, puis les limites connues
> (volume, biais, simplifications). Ne décris que ce que le code fait réellement.

#### Enrichissement des données (signes avant-coureurs)

> Le modèle de risque thermique plafonne parce que, dans la simulation, l'instant d'une
> panne est tiré au hasard. Écris un script reproductible qui ajoute une dégradation
> progressive avant une partie des pannes, des pannes sans signe et des dérives sans panne.
> Ne modifie pas les pannes elles-mêmes. Choisis les durées sur un critère physique, pas
> pour maximiser le score. Documente chaque hypothèse et trace le bilan dans un fichier.

#### Extension de l'historique

> Six mois d'historique ne suffisent pas pour départager des modèles. Prolonge la
> simulation des trois usines jusqu'à une date fixe, avec exactement les mêmes règles que les
> six premiers mois, sans modifier ceux-ci. Vérifie que le taux de panne et le delta moyen
> de l'extension sont cohérents avec l'origine. Trace le bilan dans un fichier.

#### Modèles de machine learning

> Écris un script d'entraînement pour deux cas : durée de vie restante de l'outil
> (régression) et risque de panne thermique à 24 h (classification). Compare une référence
> naïve, des régressions simples, Random Forest, Gradient Boosting, Extra Trees, gradient
> boosting par histogrammes, k plus proches voisins et un réseau de neurones en validation
> temporelle. Retiens le modèle le plus simple à moins de 1 % du meilleur. Exporte les
> modèles, leurs paramètres et leurs métriques. Interprète les résultats et dis leurs limites.

#### Plafond de performance

> Les données sont simulées : la loi qui génère les pannes est connue. Calcule la
> performance du meilleur prédicteur possible et compare-la à celle de nos modèles, sur les
> mêmes plis de validation. Dis s'il reste une marge de progression.

#### API et solution applicative

> Expose les deux modèles par une API REST : contrat d'entrée et de sortie validé, codes
> d'erreur, mode dégradé sans historique. Place les seuils d'alerte et les messages dans un
> fichier de configuration que le métier peut modifier sans code. Partage le calcul des
> variables entre l'entraînement et l'API. Décris ensuite l'ensemble : mécanismes
> d'intégration, paramétrage, règles métier, écrans et usages attendus.

#### Tableaux de bord

> Les tableaux de bord doivent se présenter comme un seul outil : une navigation commune,
> des libellés en français, aucun bouton sans effet, un clic sur un site ouvre son écran.
> Épure l'interface et vérifie chaque écran dans le navigateur.

#### Conteneurisation

> Écris les Dockerfile et le fichier Docker Compose pour lancer l'API et les quatre
> tableaux de bord avec une seule commande. Conteneurs sans privilèges, contrôle de santé
> qui exige les modèles chargés. Construis et démarre réellement les images pour vérifier.

#### Intégration continue

> Écris une chaîne GitHub Actions qui, à chaque envoi de code, analyse le code, lance les
> tests, ré-entraîne les modèles à partir des données versionnées, construit les images
> Docker et lance une prédiction réelle dans le conteneur.

## Documentation technique

#### Schéma d'architecture et choix techniques

> Rédige le document d'architecture : schéma des composants et des flux, depuis les sources
> de données jusqu'aux écrans ; rôle de chaque composant ; justification des choix au
> regard des contraintes industrielles de MECHA ; mécanismes de tolérance aux pannes ;
> architecture cible à l'échelle industrielle.

#### Plan de test et validation

> Rédige le plan de test : stratégie, jeux d'essai, cas de test avec donnée d'essai et
> résultat attendu, résultats de la campagne, cahier de recette métier, anomalies
> détectées et corrections, critères de validation techniques et fonctionnels, réserves.
> Chaque cas doit correspondre à un test qui existe dans le dépôt.

#### Déploiement, exploitation et mise en œuvre dans les usines

> Rédige le document de déploiement : exécution de la solution, intégration continue,
> exploitation courante, puis une projection de mise en œuvre progressive sur les cinq
> usines de MECHA, avec les contraintes des sites, les impacts techniques et
> organisationnels, les prérequis et les points de vigilance.

#### Enjeux RGPD

> Décris les enjeux RGPD du projet : ce que contient le prototype, et ce qu'il faudrait
> prévoir avec des données réelles (types de données, anonymisation, pseudonymisation,
> finalité, rôle du DPO, analyse d'impact).

#### Guide d'entretien et synthèse des besoins

> L'équipe n'a aucun contact avec MECHA. À partir du cahier des charges, rédige un guide
> d'entretien, identifie les profils à interroger, puis une synthèse des besoins sous
> forme de tableau « verbatim, besoin, critère d'acceptation », priorisée. Indique
> clairement que les entretiens sont simulés.

#### Compte-rendu des échanges avec l'encadrant

> Propose un compte-rendu simulé de trois points avec l'encadrant, dans son rôle de client :
> cadrage, avancement, validation. Pour chaque question : réponse, décision, impact sur le
> projet. Marque le texte comme simulé : l'équipe le corrigera avec les échanges réels.

#### Guide utilisateur métier

> Rédige un guide de deux pages pour un responsable maintenance ou production : à quoi
> sert l'outil, comment y accéder, comment lire chaque écran, comment interpréter les
> résultats, limites et conditions d'usage, que faire en cas de problème. Sans jargon.

#### Conduite du changement

> Rédige le plan de conduite du changement : ce qui change, acteurs concernés, messages
> principaux, actions pour informer, communiquer, former et faire participer, calendrier,
> mesure de l'adoption, risques et parades.

#### Matrice de conformité

> Reprends chaque exigence du cahier des charges et chaque livrable attendu. Pour chacun,
> indique le statut, la preuve et son emplacement dans le dépôt. Liste les écarts et un
> plan d'amélioration priorisé.

## Support de soutenance

> Prépare un support de 10 diapositives pour une soutenance de 20 minutes devant un jury
> technique. Style épuré et uniforme : une idée par diapositive, peu de texte, les
> chiffres clés en grand. Mets le détail dans les notes d'orateur, avec le temps de parole
> de chaque diapositive. Termine par ce qui est démontré et ce qui reste à prouver.
