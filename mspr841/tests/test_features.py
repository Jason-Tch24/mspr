"""Tests unitaires des features — dont la parité entraînement / API."""

import numpy as np
import pandas as pd
import pytest

from features import FEATURES_B, thermal_features_frame, thermal_features_from_series


def test_valeur_unique_mode_degrade():
    f = thermal_features_from_series([9.5])
    assert f == {"delta": 9.5, "delta_moy_6h": 9.5, "delta_moy_24h": 9.5,
                 "delta_min_6h": 9.5, "delta_tendance": 0.0}


def test_fenetres_et_tendance():
    serie = [12.0] * 36 + [9.0] * 12          # 24 h dont les 6 dernières heures à 9 K
    f = thermal_features_from_series(serie)
    assert f["delta_moy_6h"] == pytest.approx(9.0)
    assert f["delta_moy_24h"] == pytest.approx(11.25)
    assert f["delta_min_6h"] == 9.0
    assert f["delta_tendance"] == pytest.approx(-2.25)   # le delta baisse


def test_serie_vide_refusee():
    with pytest.raises(ValueError):
        thermal_features_from_series([])


def test_parite_entrainement_api():
    """Le calcul vectorisé (entraînement) et le calcul unitaire (API) donnent les mêmes valeurs."""
    rng = np.random.default_rng(0)
    serie = pd.Series(11.5 + rng.normal(0, 1.5, 200))
    frame = thermal_features_frame(serie)
    for i in (0, 5, 11, 12, 47, 48, 120, 199):
        unitaire = thermal_features_from_series(serie.iloc[: i + 1].tolist())
        for col in FEATURES_B:
            assert frame.loc[i, col] == pytest.approx(unitaire[col]), (i, col)
