"""
conftest.py — Configuration pytest pour le dossier dashboard/

Les modules du dashboard (store, config, simulator, kpi_engine,
alert_engine) sont des fichiers Python plats dans dashboard/.
Ce fichier ajoute ce dossier au sys.path de Python pour que pytest
puisse les importer quelle que soit la racine d'exécution.
"""

import sys
from pathlib import Path

# Ajoute dashboard/ au chemin de recherche des modules Python
# Nécessaire quand pytest est lancé depuis la racine du dépôt
sys.path.insert(0, str(Path(__file__).parent))
