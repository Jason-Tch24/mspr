"""
main.py — API de scoring IA MECHA (MSPR 841)

Expose les modèles de maintenance prédictive entraînés sur les données Gold :
  - POST /predict/rul              → RUL outil Usine A (Random Forest Regressor)
  - POST /predict/risque-thermique → Risque thermique Usine B (XGBoost Classifier)

Lancement local :
    uvicorn main:app --reload --port 8000

Documentation interactive :
    http://localhost:8000/docs
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schemas import RULInput, RULOutput, RisqueThermInput, RisqueThermOutput

# ─────────────────────────────────────────────────────────────
# CHEMINS
# ─────────────────────────────────────────────────────────────
MODELS_DIR = Path(__file__).resolve().parent / "models"

# ─────────────────────────────────────────────────────────────
# CHARGEMENT DES MODÈLES (au démarrage, une seule fois)
# ─────────────────────────────────────────────────────────────

def _load(model_file: str, meta_file: str):
    model_path = MODELS_DIR / model_file
    meta_path  = MODELS_DIR / meta_file
    if not model_path.exists():
        raise RuntimeError(
            f"Modèle introuvable : {model_path}\n"
            "Exécutez d'abord : python notebooks/ml_poc_mecha_rul_thermique.py"
        )
    model = joblib.load(model_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    return model, meta


try:
    _model_A, _meta_A = _load("rf_usine_A_rul.joblib",      "rf_usine_A_rul_meta.json")
    _model_B, _meta_B = _load("xgb_usine_B_risque.joblib",  "xgb_usine_B_risque_meta.json")
    _models_ok = True
except RuntimeError as e:
    print(f"[WARN] Modèles non chargés : {e}")
    _model_A = _model_B = _meta_A = _meta_B = None
    _models_ok = False

_FEATURES_A: list = _meta_A["features"] if _meta_A else []
_FEATURES_B: list = _meta_B["features"] if _meta_B else []

def _model_label(meta: dict | None, usine: str) -> str:
    """Construit le libellé modèle depuis le méta JSON."""
    if not meta:
        return "modèle non chargé"
    algo = meta.get("algorithme", "?")
    cv   = meta.get("metriques_cv", {})
    if meta.get("type") == "regression":
        mae = cv.get("MAE_mean", meta.get("metriques_test", {}).get("MAE", "?"))
        r2  = cv.get("R2_mean",  meta.get("metriques_test", {}).get("R2",  "?"))
        return f"{algo} · MAE={mae} sessions · R²={r2}"
    else:
        bal = cv.get("BalancedAccuracy_mean", "?")
        rec = cv.get("RecallCritique_mean",   "?")
        return f"{algo} · BalAcc={bal} · RecallCritique={rec}"

_LABEL_A = _model_label(_meta_A, "Usine_A")
_LABEL_B = _model_label(_meta_B, "Usine_B")

# ─────────────────────────────────────────────────────────────
# APPLICATION
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="MECHA IA — API de scoring maintenance prédictive",
    description=(
        "API REST exposant les modèles de machine learning développés "
        "dans le cadre du projet MECHA (MSPR 841).\n\n"
        "**Usine A** : prédiction de la durée de vie résiduelle (RUL) de l'outil de coupe.\n\n"
        "**Usine B** : classification du risque de panne thermique (Normal / Risque / Critique)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────

def _build_feature_vector_A(data: RULInput) -> pd.DataFrame:
    """
    Construit le vecteur de features pour Usine A.
    Les features de lag et rolling sont approximées par la valeur courante
    (mode single-session : pas d'historique disponible via l'API).
    """
    usure = data.usure_cumulee_pct

    row = {
        "usure_cumulee_pct"  : usure,
        "TRS"                : data.TRS,
        "temps_cycle_min"    : data.temps_cycle_min    or 45.0,
        "derive_cycle_pct"   : data.derive_cycle_pct   or 0.0,
        "disponibilite"      : data.disponibilite       or 1.0,
        "performance"        : data.performance         or 1.0,
        "qualite"            : data.qualite             or 1.0,
        "consommation_kwh"   : data.consommation_kwh    or 3.1,
        "vitesse_rotation_rpm": data.vitesse_rotation_rpm or 1500.0,
        "couple_nm"          : data.couple_nm           or 40.0,
        "taux_rebut"         : data.taux_rebut          or 0.04,
        # Lags approximés par la valeur courante (single-session)
        "usure_lag_1"        : usure,
        "usure_lag_2"        : usure,
        "usure_lag_3"        : usure,
        "usure_lag_5"        : usure,
        # Rolling means = valeur courante, stds = 0
        "usure_roll_mean_5"  : usure,
        "usure_roll_std_5"   : 0.0,
        "usure_roll_mean_10" : usure,
        "usure_roll_std_10"  : 0.0,
        "usure_roll_mean_20" : usure,
        "usure_roll_std_20"  : 0.0,
        "usure_delta"        : 0.0,
    }
    df = pd.DataFrame([row])
    # Aligner sur les features exactes du modèle
    for col in _FEATURES_A:
        if col not in df.columns:
            df[col] = 0.0
    return df[_FEATURES_A]


def _build_feature_vector_B(data: RisqueThermInput) -> pd.DataFrame:
    """
    Construit le vecteur de features pour Usine B.
    Même principe d'approximation single-session pour lags/rolling.
    """
    delta  = data.temp_process_delta
    temp_c = data.temp_process_c or (delta + 23.0)  # estimation si absent
    usure  = data.usure_cumulee_pct or 42.0

    row = {
        "temp_process_delta"      : delta,
        "TRS"                     : data.TRS,
        "taux_rebut"              : data.taux_rebut              or 0.03,
        "disponibilite"           : data.disponibilite           or 1.0,
        "performance"             : data.performance             or 1.0,
        "consommation_kwh"        : data.consommation_kwh        or 3.5,
        "temps_cycle_min"         : data.temps_cycle_min         or 40.0,
        "derive_cycle_pct"        : data.derive_cycle_pct        or 0.0,
        "nb_pannes_7j"            : data.nb_pannes_7j            or 0,
        "temp_process_c"          : temp_c,
        "usure_cumulee_pct"       : usure,
        "couple_nm"               : data.couple_nm               or 45.0,
        "vitesse_rotation_rpm"    : data.vitesse_rotation_rpm    or 1530.0,
        "indice_stabilite_process": data.indice_stabilite_process or 0.9,
        "panne_usure_outil"       : data.panne_usure_outil       or 0,
        # Lags delta approximés
        "delta_lag_1"             : delta,
        "delta_lag_2"             : delta,
        "delta_lag_3"             : delta,
        "delta_lag_5"             : delta,
        # Rolling delta
        "delta_roll_mean_5"       : delta,
        "delta_roll_std_5"        : 0.0,
        "delta_roll_mean_10"      : delta,
        "delta_roll_std_10"       : 0.0,
        "delta_roll_mean_20"      : delta,
        "delta_roll_std_20"       : 0.0,
        "delta_deriv"             : 0.0,
        "delta_deriv2"            : 0.0,
        # Rolling temp_c
        "temp_c_roll_mean_5"      : temp_c,
        "temp_c_roll_mean_10"     : temp_c,
        "temp_c_deriv"            : 0.0,
        # Rolling usure
        "usure_roll_mean_10"      : usure,
    }
    df = pd.DataFrame([row])
    for col in _FEATURES_B:
        if col not in df.columns:
            df[col] = 0.0
    return df[_FEATURES_B]


def _rul_alerte(rul_sessions: float) -> str:
    if rul_sessions <= 10:
        return "CRITICAL"
    if rul_sessions <= 20:
        return "WARNING"
    return "OK"


def _risque_alerte(label: int) -> str:
    return {0: "OK", 1: "WARNING", 2: "CRITICAL"}.get(label, "OK")


# ─────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.get("/", summary="Santé de l'API")
def health():
    return {
        "status"     : "ok",
        "modeles_ok" : _models_ok,
        "usine_A"    : "rf_usine_A_rul.joblib" if _models_ok else "non chargé",
        "usine_B"    : "xgb_usine_B_risque.joblib" if _models_ok else "non chargé",
    }


@app.post(
    "/predict/rul",
    response_model=RULOutput,
    summary="Usine A — Prédiction RUL outil de coupe",
    tags=["Usine A"],
)
def predict_rul(data: RULInput) -> RULOutput:
    """
    Prédit la durée de vie résiduelle (RUL) de l'outil de coupe de l'Usine A.

    - **rul_sessions** : nombre de sessions de 30 min restantes avant remplacement
    - **rul_heures** : équivalent en heures
    - **niveau_alerte** : CRITICAL (≤10 sessions) · WARNING (≤20) · OK

    > *Mode single-session* : les features de lag/rolling sont approximées
    > par la valeur courante. Pour une précision maximale, alimenter l'API
    > avec des valeurs préagrégées côté client.
    """
    if not _models_ok:
        raise HTTPException(503, "Modèles non disponibles — exécutez d'abord le script ML")

    X = _build_feature_vector_A(data)
    rul_raw = float(_model_A.predict(X)[0])
    rul     = max(0.0, round(rul_raw, 1))
    alerte  = _rul_alerte(rul)

    if alerte == "CRITICAL":
        msg = f"Remplacement outil IMMINENT — {rul:.0f} session(s) restante(s) ({rul * 0.5:.1f}h). Planifier l'intervention maintenant."
    elif alerte == "WARNING":
        msg = f"Remplacement outil dans {rul:.0f} sessions ({rul * 0.5:.1f}h). Anticiper la commande de pièce."
    else:
        msg = f"Outil en bon état — {rul:.0f} sessions restantes ({rul * 0.5:.1f}h) avant prochain remplacement."

    return RULOutput(
        usine             = "Usine_A",
        rul_sessions      = rul,
        rul_heures        = round(rul * 0.5, 1),
        usure_cumulee_pct = data.usure_cumulee_pct,
        niveau_alerte     = alerte,
        interpretation    = msg,
        modele            = _LABEL_A,
    )


@app.post(
    "/predict/risque-thermique",
    response_model=RisqueThermOutput,
    summary="Usine B — Classification du risque de panne thermique",
    tags=["Usine B"],
)
def predict_risque_thermique(data: RisqueThermInput) -> RisqueThermOutput:
    """
    Classifie le risque de panne thermique de l'Usine B.

    - **0 — Normal** : aucune panne thermique détectée dans les prochaines 48 sessions
    - **1 — Risque** : panne possible dans les 4 à 48 sessions (2h–24h)
    - **2 — Critique** : panne imminente dans les 3 prochaines sessions (1h30)

    > *Note* : modèle entraîné sur données simulées. Recalibration sur données
    > terrain recommandée avant déploiement en production.
    """
    if not _models_ok:
        raise HTTPException(503, "Modèles non disponibles — exécutez d'abord le script ML")

    X      = _build_feature_vector_B(data)
    label  = int(_model_B.predict(X)[0])
    probas = _model_B.predict_proba(X)[0]

    noms   = {0: "Normal", 1: "Risque", 2: "Critique"}
    msgs   = {
        0: "Fonctionnement normal — aucune panne thermique détectée dans les prochaines 24h.",
        1: "Risque thermique détecté — vérifier le système de refroidissement dans les prochaines heures.",
        2: "PANNE THERMIQUE IMMINENTE — intervention maintenance requise immédiatement. Arrêt machine recommandé.",
    }

    return RisqueThermOutput(
        usine          = "Usine_B",
        risque_label   = label,
        risque_nom     = noms[label],
        probabilites   = {
            "Normal"   : round(float(probas[0]), 4),
            "Risque"   : round(float(probas[1]), 4),
            "Critique" : round(float(probas[2]), 4),
        },
        niveau_alerte  = _risque_alerte(label),
        interpretation = msgs[label],
        modele         = _LABEL_B,
    )
