"""
features.py — Construction des variables d'entrée des modèles MECHA.

Ce module est la SEULE définition des features : il est importé à la fois par
le script d'entraînement (mspr841/ml/train_models.py) et par l'API (main.py).
On garantit ainsi que le modèle reçoit en production exactement les mêmes
variables que celles sur lesquelles il a été entraîné (pas d'écart
entraînement / service).
"""

from __future__ import annotations

import pandas as pd

# ─────────────────────────────────────────────────────────────
# USINE A — RUL de l'outil de coupe
# Variables instantanées uniquement : une seule mesure suffit pour scorer.
# ─────────────────────────────────────────────────────────────
FEATURES_A: list[str] = [
    "usure_cumulee_pct",
    "TRS",
    "temps_cycle_min",
    "derive_cycle_pct",
    "disponibilite",
    "performance",
    "qualite",
    "consommation_kwh",
    "vitesse_rotation_rpm",
    "couple_nm",
    "taux_rebut",
]

# ─────────────────────────────────────────────────────────────
# USINE B — Risque de panne thermique à 24 h
# Le risque dépend du RÉGIME thermique (niveau moyen et tendance du delta
# process/air), pas de la seule valeur instantanée, très bruitée.
# 1 session = 30 min → 12 sessions = 6 h, 48 sessions = 24 h.
# ─────────────────────────────────────────────────────────────
FENETRE_COURTE = 12
FENETRE_LONGUE = 48

FEATURES_B: list[str] = [
    "delta",            # delta thermique de la session courante (K)
    "delta_moy_6h",     # moyenne sur les 12 dernières sessions
    "delta_moy_24h",    # moyenne sur les 48 dernières sessions
    "delta_min_6h",     # minimum sur les 12 dernières sessions
    "delta_tendance",   # moy 6 h − moy 24 h (négatif = le delta baisse)
]


def thermal_features_from_series(valeurs: list[float]) -> dict[str, float]:
    """
    Features thermiques à partir d'une série chronologique de deltas
    (la plus ancienne en premier, la session courante en dernier).

    Avec une seule valeur (pas d'historique), toutes les moyennes valent la
    valeur courante et la tendance vaut 0 : c'est le « mode dégradé » de l'API.
    """
    if not valeurs:
        raise ValueError("Au moins une valeur de delta thermique est requise")
    court = valeurs[-FENETRE_COURTE:]
    long_ = valeurs[-FENETRE_LONGUE:]
    moy_court = sum(court) / len(court)
    moy_long = sum(long_) / len(long_)
    return {
        "delta": float(valeurs[-1]),
        "delta_moy_6h": float(moy_court),
        "delta_moy_24h": float(moy_long),
        "delta_min_6h": float(min(court)),
        "delta_tendance": float(moy_court - moy_long),
    }


def thermal_features_frame(delta: pd.Series) -> pd.DataFrame:
    """
    Version vectorisée (entraînement) : mêmes définitions que
    thermal_features_from_series, calculées pour chaque session d'une série
    triée chronologiquement. Les fenêtres sont causales (passé + présent).
    """
    moy_court = delta.rolling(FENETRE_COURTE, min_periods=1).mean()
    moy_long = delta.rolling(FENETRE_LONGUE, min_periods=1).mean()
    return pd.DataFrame(
        {
            "delta": delta.astype(float),
            "delta_moy_6h": moy_court,
            "delta_moy_24h": moy_long,
            "delta_min_6h": delta.rolling(FENETRE_COURTE, min_periods=1).min(),
            "delta_tendance": moy_court - moy_long,
        }
    )[FEATURES_B]
