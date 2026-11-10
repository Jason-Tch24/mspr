"""Configuration pytest de l'API : rend mspr841/api importable et fournit le client de test."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    import main

    assert main._models_ok, "Modèles absents : lancer python mspr841/ml/train_models.py"
    return TestClient(main.app)
