"""
main.py — API de scoring IA MECHA (MSPR TPRE841)

Expose les modèles de maintenance prédictive entraînés sur les données Gold :
  - POST /predict/rul              → durée de vie résiduelle de l'outil (Usine A)
  - POST /predict/risque-thermique → risque de panne thermique à 24 h (Usine B)
  - GET  /                         → état de santé (utilisé par le healthcheck Docker)
  - GET  /models                   → métadonnées et métriques des modèles chargés
  - GET  /regles                   → règles métier actives (seuils, messages)

Lancement local (depuis mspr841/api) :
    uvicorn main:app --reload --port 8000
Documentation interactive : http://localhost:8000/docs

Variables d'environnement :
    MECHA_MODELS_DIR   dossier des modèles         (défaut : ./models)
    MECHA_REGLES_PATH  fichier de règles métier    (défaut : ./regles_metier.json)
"""

import json
import os
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from features import FEATURES_A, FEATURES_B, FENETRE_LONGUE, thermal_features_from_series
from schemas import RULInput, RULOutput, RisqueThermInput, RisqueThermOutput

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = Path(os.environ.get("MECHA_MODELS_DIR", BASE_DIR / "models"))
REGLES_PATH = Path(os.environ.get("MECHA_REGLES_PATH", BASE_DIR / "regles_metier.json"))

# ─────────────────────────────────────────────────────────────
# CHARGEMENT (une seule fois, au démarrage)
# ─────────────────────────────────────────────────────────────

REGLES: dict = json.loads(REGLES_PATH.read_text(encoding="utf-8"))
SESSION_H: float = REGLES["session_duree_min"] / 60


def _load(nom: str):
    chemin = MODELS_DIR / f"{nom}.joblib"
    if not chemin.exists():
        raise RuntimeError(
            f"Modèle introuvable : {chemin} — exécutez : python mspr841/ml/train_models.py"
        )
    meta = json.loads((MODELS_DIR / f"{nom}_meta.json").read_text(encoding="utf-8"))
    return joblib.load(chemin), meta


try:
    _model_A, _meta_A = _load("usine_A_rul")
    _model_B, _meta_B = _load("usine_B_risque")
    _models_ok = True
except (RuntimeError, OSError) as e:
    # Mode dégradé : l'API démarre et répond 503 sur les prédictions.
    print(f"[WARN] Modèles non chargés : {e}")
    _model_A = _model_B = _meta_A = _meta_B = None
    _models_ok = False


def _model_label(meta: dict | None) -> str:
    """Libellé affiché dans les dashboards, construit depuis les métadonnées."""
    if not meta:
        return "modèle non chargé"
    cv = meta.get("metriques_cv", {})
    if meta.get("type") == "regression":
        return f"{meta['algorithme']} · MAE={cv.get('MAE', '?')} sessions · R²={cv.get('R2', '?')}"
    return f"{meta['algorithme']} · AUC={cv.get('ROC_AUC', '?')} · PR-AUC={cv.get('PR_AUC', '?')}"


# ─────────────────────────────────────────────────────────────
# RÈGLES MÉTIER (seuils lus dans regles_metier.json)
# ─────────────────────────────────────────────────────────────

def niveau_alerte_rul(rul_sessions: float) -> str:
    regles = REGLES["usine_A"]
    if rul_sessions <= regles["rul_critical_sessions"]:
        return "CRITICAL"
    if rul_sessions <= regles["rul_warning_sessions"]:
        return "WARNING"
    return "OK"


def niveau_alerte_risque(proba: float) -> str:
    regles = REGLES["usine_B"]
    if proba >= regles["seuil_critical"]:
        return "CRITICAL"
    if proba >= regles["seuil_warning"]:
        return "WARNING"
    return "OK"


# ─────────────────────────────────────────────────────────────
# APPLICATION
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="MECHA IA — API de scoring maintenance prédictive",
    description=(
        "API REST exposant les modèles de machine learning du projet MECHA (MSPR TPRE841).\n\n"
        "**Usine A** : durée de vie résiduelle (RUL) de l'outil de coupe.\n\n"
        "**Usine B** : probabilité de panne thermique dans les 24 h, traduite en niveau d'alerte."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _exiger_modeles() -> None:
    if not _models_ok:
        raise HTTPException(503, "Modèles non disponibles — exécutez mspr841/ml/train_models.py")


@app.get("/", summary="Santé de l'API", tags=["Supervision"])
def health():
    return {
        "status": "ok",
        "modeles_ok": _models_ok,
        "usine_A": _meta_A["algorithme"] if _models_ok else "non chargé",
        "usine_B": _meta_B["algorithme"] if _models_ok else "non chargé",
    }


@app.get("/models", summary="Métadonnées et métriques des modèles", tags=["Supervision"])
def models():
    _exiger_modeles()
    return {"usine_A": _meta_A, "usine_B": _meta_B}


@app.get("/regles", summary="Règles métier actives (seuils, messages)", tags=["Supervision"])
def regles():
    return REGLES


@app.post("/predict/rul", response_model=RULOutput,
          summary="Usine A — Prédiction RUL outil de coupe", tags=["Usine A"])
def predict_rul(data: RULInput) -> RULOutput:
    """
    Prédit la durée de vie résiduelle (RUL) de l'outil de coupe de l'Usine A.

    - **rul_sessions** : sessions de 30 min restantes avant remplacement
    - **niveau_alerte** : CRITICAL / WARNING / OK selon les seuils de `regles_metier.json`

    Les champs optionnels absents sont remplacés par la médiane d'entraînement.
    """
    _exiger_modeles()
    defauts = _meta_A["valeurs_par_defaut"]
    saisie = data.model_dump()
    ligne = {c: saisie[c] if saisie.get(c) is not None else defauts[c] for c in FEATURES_A}
    rul = max(0.0, round(float(_model_A.predict(pd.DataFrame([ligne])[FEATURES_A])[0]), 1))
    alerte = niveau_alerte_rul(rul)
    heures = round(rul * SESSION_H, 1)

    return RULOutput(
        usine="Usine_A",
        rul_sessions=rul,
        rul_heures=heures,
        usure_cumulee_pct=data.usure_cumulee_pct,
        niveau_alerte=alerte,
        interpretation=REGLES["usine_A"]["messages"][alerte].format(rul=rul, heures=heures),
        modele=_model_label(_meta_A),
    )


@app.post("/predict/risque-thermique", response_model=RisqueThermOutput,
          summary="Usine B — Risque de panne thermique à 24 h", tags=["Usine B"])
def predict_risque_thermique(data: RisqueThermInput) -> RisqueThermOutput:
    """
    Estime la probabilité d'au moins une panne thermique dans les 24 prochaines heures.

    Le risque augmente quand le delta thermique process/air **baisse** (dissipation
    insuffisante). Le niveau d'alerte découle des seuils de `regles_metier.json`.

    Sans `historique_delta`, la réponse est calculée en *mode dégradé*
    (`mode_degrade = true`) à partir de la seule valeur courante.
    """
    _exiger_modeles()
    historique = list(data.historique_delta or [])[-(FENETRE_LONGUE - 1):]
    serie = historique + [data.temp_process_delta]
    X = pd.DataFrame([thermal_features_from_series(serie)])[FEATURES_B]
    proba = round(float(_model_B.predict_proba(X)[0, 1]), 4)
    alerte = niveau_alerte_risque(proba)
    regles_b = REGLES["usine_B"]

    return RisqueThermOutput(
        usine="Usine_B",
        probabilite_panne_24h=proba,
        risque_label={"OK": 0, "WARNING": 1, "CRITICAL": 2}[alerte],
        risque_nom=regles_b["noms"][alerte],
        probabilites={"Normal": round(1 - proba, 4), "À risque": proba},
        niveau_alerte=alerte,
        interpretation=regles_b["messages"][alerte].format(proba=proba),
        mode_degrade=not historique,
        nb_sessions_historique=len(historique),
        modele=_model_label(_meta_B),
    )
