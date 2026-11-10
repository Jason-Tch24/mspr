"""
Tests d'intégration de l'API de scoring (FastAPI TestClient).
Chaque test porte l'identifiant du cas correspondant dans docs/05_plan_de_test.md.
"""

import pytest

import main

REGLES = main.REGLES


# ── Supervision ───────────────────────────────────────────────

def test_API01_sante(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["modeles_ok"] is True


def test_API02_metadonnees_modeles(client):
    meta = client.get("/models").json()
    assert meta["usine_A"]["type"] == "regression"
    assert meta["usine_B"]["horizon_sessions"] == REGLES["usine_B"]["horizon_sessions"]


def test_API03_regles_exposees(client):
    assert client.get("/regles").json()["usine_B"]["seuil_warning"] == REGLES["usine_B"]["seuil_warning"]


# ── Usine A — RUL ─────────────────────────────────────────────

def _rul(client, usure, **extra):
    r = client.post("/predict/rul", json={"usure_cumulee_pct": usure, "TRS": 0.9, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_A01_outil_neuf_ok(client):
    rep = _rul(client, 5)
    assert rep["niveau_alerte"] == "OK"
    assert rep["rul_sessions"] > REGLES["usine_A"]["rul_warning_sessions"]


def test_A02_outil_use_critique(client):
    rep = _rul(client, 88)
    assert rep["niveau_alerte"] == "CRITICAL"
    assert "IMMINENT" in rep["interpretation"]


def test_A03_rul_decroit_avec_l_usure(client):
    ruls = [_rul(client, u)["rul_sessions"] for u in (0, 20, 40, 60, 80, 90)]
    assert ruls == sorted(ruls, reverse=True)
    assert ruls[-1] >= 0


def test_A04_heures_coherentes_avec_sessions(client):
    rep = _rul(client, 45)
    assert rep["rul_heures"] == pytest.approx(rep["rul_sessions"] * 0.5, abs=0.06)


def test_A05_rul_jamais_negative(client):
    assert _rul(client, 100)["rul_sessions"] == 0.0


@pytest.mark.parametrize("corps", [
    {"usure_cumulee_pct": 120, "TRS": 0.9},      # usure hors bornes
    {"usure_cumulee_pct": 50, "TRS": 1.4},       # TRS hors bornes
    {"TRS": 0.9},                                # champ obligatoire absent
    {"usure_cumulee_pct": "abc", "TRS": 0.9},    # mauvais type
])
def test_A06_entrees_invalides_refusees(client, corps):
    assert client.post("/predict/rul", json=corps).status_code == 422


@pytest.mark.parametrize("rul,attendu", [(0, "CRITICAL"), (10, "CRITICAL"), (10.1, "WARNING"),
                                         (20, "WARNING"), (20.1, "OK"), (60, "OK")])
def test_A07_seuils_alerte_rul(rul, attendu):
    assert main.niveau_alerte_rul(rul) == attendu


# ── Usine B — risque thermique ────────────────────────────────

def _risque(client, delta, historique=None):
    corps = {"temp_process_delta": delta}
    if historique is not None:
        corps["historique_delta"] = historique
    r = client.post("/predict/risque-thermique", json=corps)
    assert r.status_code == 200, r.text
    return r.json()


def test_B01_regime_nominal_normal(client):
    rep = _risque(client, 13.5, [13.5] * 47)
    assert rep["niveau_alerte"] == "OK" and rep["risque_nom"] == "Normal"
    assert rep["mode_degrade"] is False and rep["nb_sessions_historique"] == 47


def test_B02_dissipation_degradee_critique(client):
    rep = _risque(client, 7.8, [7.8] * 47)
    assert rep["niveau_alerte"] == "CRITICAL" and rep["risque_label"] == 2


def test_B03_risque_croit_quand_le_delta_baisse(client):
    probas = [_risque(client, d, [d] * 47)["probabilite_panne_24h"] for d in (15, 13, 11, 9.5, 8.5, 7.5)]
    assert probas == sorted(probas)


def test_B04_mode_degrade_sans_historique(client):
    rep = _risque(client, 9.0)
    assert rep["mode_degrade"] is True and rep["nb_sessions_historique"] == 0


def test_B05_l_historique_compte(client):
    """Même mesure courante, régimes différents : le risque doit différer."""
    apres_regime_bas = _risque(client, 10.5, [8.5] * 47)["probabilite_panne_24h"]
    apres_regime_haut = _risque(client, 10.5, [13.5] * 47)["probabilite_panne_24h"]
    assert apres_regime_bas > apres_regime_haut


def test_B06_probabilites_coherentes(client):
    rep = _risque(client, 10.0, [10.0] * 20)
    assert 0 <= rep["probabilite_panne_24h"] <= 1
    assert sum(rep["probabilites"].values()) == pytest.approx(1.0, abs=1e-3)


def test_B07_historique_long_tronque(client):
    rep = _risque(client, 11.0, [11.0] * 300)
    assert rep["nb_sessions_historique"] == 47


@pytest.mark.parametrize("corps", [
    {"temp_process_delta": -3},
    {"temp_process_delta": 9, "historique_delta": "abc"},
    {},
])
def test_B08_entrees_invalides_refusees(client, corps):
    assert client.post("/predict/risque-thermique", json=corps).status_code == 422


def test_B09_seuils_alerte_risque():
    w, c = REGLES["usine_B"]["seuil_warning"], REGLES["usine_B"]["seuil_critical"]
    assert main.niveau_alerte_risque(w - 0.01) == "OK"
    assert main.niveau_alerte_risque(w) == "WARNING"
    assert main.niveau_alerte_risque(c - 0.01) == "WARNING"
    assert main.niveau_alerte_risque(c) == "CRITICAL"


def test_B10_compatibilite_payload_dashboard(client):
    """Le dashboard envoie aussi ses KPIs courants : ils doivent être acceptés."""
    corps = {"temp_process_delta": 10.2, "TRS": 0.93, "taux_rebut": 0.03, "nb_pannes_7j": 2,
             "usure_cumulee_pct": 42.0, "vitesse_rotation_rpm": 1530, "historique_delta": [10.4, 10.1]}
    assert client.post("/predict/risque-thermique", json=corps).status_code == 200


# ── Garde-fous qualité des modèles (non-régression) ───────────

def test_Q01_modele_A_bat_la_reference_naive():
    bench = main._meta_A["benchmark"]
    assert main._meta_A["metriques_cv"]["MAE"] < 0.2 * bench["Moyenne (référence naïve)"]["MAE"]


def test_Q02_modele_B_au_dessus_du_hasard():
    assert main._meta_B["metriques_cv"]["ROC_AUC"] >= 0.70


def test_Q03_niveaux_d_alerte_ordonnes_par_risque_reel():
    """En validation, plus le niveau est élevé, plus le taux de panne observé est élevé."""
    n = main._meta_B["lecture_metier_des_seuils"]["niveaux"]
    assert n["OK"]["taux_panne_24h_observe"] < n["WARNING"]["taux_panne_24h_observe"] < n["CRITICAL"]["taux_panne_24h_observe"]
