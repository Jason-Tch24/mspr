"""
conftest.py — Configuration pytest pour le dossier dashboard/

Ajoute dashboard/ au sys.path (les modules store, config, simulator… sont des
fichiers plats) et fournit la fixture `simulateur`, qui démarre le simulateur
une seule fois pour toute la session de tests.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(scope="session")
def simulateur():
    """Simulateur démarré, avec au moins une session rejouée par usine."""
    import config
    import simulator
    import store

    simulator.start()
    limite = time.time() + 30
    while time.time() < limite:
        if all(len(store.get_buffer(u)) >= 2 for u in config.USINES):
            break
        time.sleep(0.5)
    else:
        simulator.stop()
        pytest.fail("Le simulateur n'a alimenté aucun buffer en 30 s")
    yield simulator
    simulator.stop()
