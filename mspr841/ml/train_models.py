"""
train_models.py — Entraînement et sélection des modèles MECHA (MSPR TPRE841)

  Usine A : régression — durée de vie résiduelle (RUL) de l'outil de coupe,
            en nombre de sessions de 30 min avant le prochain remplacement.
  Usine B : classification binaire — « à risque » = au moins une panne
            thermique dans les 24 prochaines heures (48 sessions).

Démarche (identique pour les deux cas) :
  1. cible construite uniquement à partir du futur de la série ;
  2. variables définies dans mspr841/api/features.py (partagées avec l'API) ;
  3. comparaison de plusieurs modèles, dont des références simples,
     en validation temporelle « walk-forward » (TimeSeriesSplit, 5 plis) ;
  4. choix du modèle LE PLUS SIMPLE dont la performance est à moins de 1 %
     du meilleur (principe de parcimonie) ;
  5. ré-entraînement sur tout l'historique, export joblib + métadonnées.

Lancement (depuis la racine du dépôt) :
    python mspr841/ml/train_models.py

Sorties :
    mspr841/api/models/usine_A_rul.joblib         + usine_A_rul_meta.json
    mspr841/api/models/usine_B_risque.joblib      + usine_B_risque_meta.json
    reports/benchmark_841.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "mspr841" / "api"
sys.path.insert(0, str(API_DIR))

from features import FEATURES_A, FEATURES_B, thermal_features_frame  # noqa: E402

GOLD = ROOT / "data" / "gold"
MODELS_DIR = API_DIR / "models"
REPORTS_DIR = ROOT / "reports"
REGLES = json.loads((API_DIR / "regles_metier.json").read_text(encoding="utf-8"))

N_SPLITS = 5
TOLERANCE_PARCIMONIE = 0.01
SEED = 42
HORIZON_B = REGLES["usine_B"]["horizon_sessions"]


def _colonne(nom: str) -> ColumnTransformer:
    """Sélectionne une seule colonne (pour les modèles de référence)."""
    return ColumnTransformer([("selection", "passthrough", [nom])])


def _choisir(resultats: dict, metrique: str, plus_grand_mieux: bool) -> str:
    """Modèle le plus simple à moins de 1 % du meilleur (ordre du dict = simplicité)."""
    valeurs = {k: v[metrique] for k, v in resultats.items() if not v.get("reference")}
    meilleur = max(valeurs.values()) if plus_grand_mieux else min(valeurs.values())
    for nom, val in valeurs.items():
        ecart = (meilleur - val) / abs(meilleur) if plus_grand_mieux else (val - meilleur) / abs(meilleur)
        if ecart <= TOLERANCE_PARCIMONIE:
            return nom
    raise RuntimeError("aucun modèle sélectionné")


# ═════════════════════════════════════════════════════════════
# USINE A — RUL
# ═════════════════════════════════════════════════════════════

def preparer_usine_A() -> tuple[pd.DataFrame, pd.Series]:
    # Historique étendu (etendre_historique_AC.py) : les six mois du Gold, prolongés
    # par simulation avec les mêmes règles. À défaut, les six mois seuls.
    fichier = GOLD / "usine_A_historique.parquet"
    if not fichier.exists():
        fichier = GOLD / "usine_A.parquet"
    df = pd.read_parquet(fichier).sort_values("timestamp").reset_index(drop=True)
    remplacement = df["remplacement_outil"].to_numpy()
    rul = np.full(len(df), np.nan)
    prochain = None
    for i in range(len(df) - 1, -1, -1):
        if remplacement[i] == 1:
            prochain = i
        if prochain is not None:
            rul[i] = prochain - i
    df["rul"] = rul
    # On écarte les sessions après le dernier remplacement (RUL inconnue)
    # et les sessions de remplacement elles-mêmes (RUL = 0).
    df = df[df["rul"] > 0]
    return df[FEATURES_A], df["rul"]


def candidats_A() -> dict:
    # Ordonnés du plus simple au plus complexe.
    return {
        "Moyenne (référence naïve)": DummyRegressor(strategy="mean"),
        "Linéaire sur l'usure seule": make_pipeline(_colonne("usure_cumulee_pct"), LinearRegression()),
        "Ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=200, min_samples_leaf=5, random_state=SEED, n_jobs=1),
        "GradientBoostingRegressor": GradientBoostingRegressor(random_state=SEED),
        "ExtraTreesRegressor": ExtraTreesRegressor(
            n_estimators=200, min_samples_leaf=5, random_state=SEED, n_jobs=1),
        "HistGradientBoostingRegressor": HistGradientBoostingRegressor(
            max_depth=3, max_iter=200, learning_rate=0.05, random_state=SEED),
        "k plus proches voisins": make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=25)),
        "Réseau de neurones (MLP)": make_pipeline(StandardScaler(), MLPRegressor(
            hidden_layer_sizes=(32, 16), max_iter=500, early_stopping=True, random_state=SEED)),
    }


def entrainer_usine_A() -> dict:
    X, y = preparer_usine_A()
    resultats = {}
    for nom, modele in candidats_A().items():
        mae, rmse, r2 = [], [], []
        for tr, te in TimeSeriesSplit(N_SPLITS).split(X):
            modele.fit(X.iloc[tr], y.iloc[tr])
            pred = modele.predict(X.iloc[te])
            mae.append(mean_absolute_error(y.iloc[te], pred))
            rmse.append(root_mean_squared_error(y.iloc[te], pred))
            r2.append(r2_score(y.iloc[te], pred))
        resultats[nom] = {
            "MAE": round(float(np.mean(mae)), 3),
            "MAE_ecart_type": round(float(np.std(mae)), 3),
            "RMSE": round(float(np.mean(rmse)), 3),
            "R2": round(float(np.mean(r2)), 4),
        }
        print(f"  A · {nom:32s} MAE={resultats[nom]['MAE']:.3f}  R²={resultats[nom]['R2']:.4f}")
    resultats["Moyenne (référence naïve)"]["reference"] = True

    retenu = _choisir(resultats, "MAE", plus_grand_mieux=False)
    modele = candidats_A()[retenu].fit(X, y)
    joblib.dump(modele, MODELS_DIR / "usine_A_rul.joblib")

    meta = {
        "usine": "Usine_A",
        "type": "regression",
        "cible": "Sessions de 30 min restantes avant le prochain remplacement d'outil",
        "algorithme": retenu,
        "features": FEATURES_A,
        "valeurs_par_defaut": {c: round(float(X[c].median()), 4) for c in FEATURES_A},
        "n_sessions_entrainement": int(len(X)),
        "validation": f"TimeSeriesSplit walk-forward, {N_SPLITS} plis",
        "metriques_cv": resultats[retenu],
        "benchmark": resultats,
        "limite_connue": (
            "Dans les données simulées, l'usure cumulée progresse quasi linéairement : "
            "la RUL se déduit presque directement de l'usure, d'où un R² très élevé "
            "même pour un modèle linéaire. Ce score ne préjuge pas de la performance "
            "sur des machines réelles (usure non linéaire, casse brutale)."
        ),
    }
    return meta


# ═════════════════════════════════════════════════════════════
# USINE B — Risque thermique à 24 h
# ═════════════════════════════════════════════════════════════

def preparer_usine_B() -> tuple[pd.DataFrame, pd.Series]:
    # Historique étendu (etendre_historique_B.py) : les six mois du Gold, prolongés
    # par simulation avec les mêmes règles. À défaut, les six mois seuls.
    fichier = GOLD / "usine_B_historique.parquet"
    if not fichier.exists():
        fichier = GOLD / "usine_B.parquet"
    df = pd.read_parquet(fichier).sort_values("timestamp").reset_index(drop=True)
    panne = df["panne_thermique"].to_numpy()
    n = len(df)
    # Cible : au moins une panne thermique dans les HORIZON_B sessions SUIVANTES
    # (la session courante est exclue : on prédit, on ne constate pas).
    cumul = np.concatenate([[0], np.cumsum(panne)])
    idx = np.arange(n)
    fin = np.minimum(idx + 1 + HORIZON_B, n)
    cible = (cumul[fin] - cumul[idx + 1] > 0).astype(int)
    X = thermal_features_frame(df["temp_process_delta"])
    # Les HORIZON_B dernières sessions n'ont pas un futur complet : écartées.
    garder = idx < n - HORIZON_B
    return X[garder].reset_index(drop=True), pd.Series(cible[garder], name="a_risque")


def candidats_B() -> dict:
    return {
        "Fréquence de base (référence naïve)": DummyClassifier(strategy="prior"),
        "Régression logistique sur le delta instantané": make_pipeline(
            _colonne("delta"), StandardScaler(), LogisticRegression(max_iter=1000)),
        "Régression logistique": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=20, random_state=SEED, n_jobs=1),
        "GradientBoostingClassifier": GradientBoostingClassifier(
            n_estimators=150, max_depth=2, random_state=SEED),
        "ExtraTreesClassifier": ExtraTreesClassifier(
            n_estimators=300, min_samples_leaf=20, random_state=SEED, n_jobs=1),
        "HistGradientBoostingClassifier": HistGradientBoostingClassifier(
            max_depth=3, max_iter=150, learning_rate=0.05, l2_regularization=1.0, random_state=SEED),
        "k plus proches voisins": make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=75)),
        "Réseau de neurones (MLP)": make_pipeline(StandardScaler(), MLPClassifier(
            hidden_layer_sizes=(32, 16), max_iter=300, early_stopping=True, random_state=SEED)),
    }


def entrainer_usine_B() -> dict:
    X, y = preparer_usine_B()
    # gap = horizon : aucune session d'entraînement ne « voit » le futur du pli de test.
    cv = TimeSeriesSplit(N_SPLITS, gap=HORIZON_B)
    resultats, hors_pli = {}, {}
    for nom, modele in candidats_B().items():
        auc, ap, brier = [], [], []
        scores = np.full(len(X), np.nan)
        for tr, te in cv.split(X):
            modele.fit(X.iloc[tr], y.iloc[tr])
            p = modele.predict_proba(X.iloc[te])[:, 1]
            scores[te] = p
            auc.append(roc_auc_score(y.iloc[te], p))
            ap.append(average_precision_score(y.iloc[te], p))
            brier.append(brier_score_loss(y.iloc[te], p))
        resultats[nom] = {
            "ROC_AUC": round(float(np.mean(auc)), 3),
            "ROC_AUC_ecart_type": round(float(np.std(auc)), 3),
            "PR_AUC": round(float(np.mean(ap)), 3),
            "Brier": round(float(np.mean(brier)), 4),
        }
        hors_pli[nom] = scores
        print(f"  B · {nom:46s} AUC={resultats[nom]['ROC_AUC']:.3f}  PR-AUC={resultats[nom]['PR_AUC']:.3f}")
    resultats["Fréquence de base (référence naïve)"]["reference"] = True

    retenu = _choisir(resultats, "ROC_AUC", plus_grand_mieux=True)

    # Lecture métier des seuils d'alerte sur les prédictions hors pli :
    # pour chaque niveau, part des sessions et taux de panne réellement observé.
    s = hors_pli[retenu]
    ok = ~np.isnan(s)
    s, yv = s[ok], y.to_numpy()[ok]
    seuil_w = REGLES["usine_B"]["seuil_warning"]
    seuil_c = REGLES["usine_B"]["seuil_critical"]
    niveaux = {}
    for nom_niv, masque in {
        "OK": s < seuil_w,
        "WARNING": (s >= seuil_w) & (s < seuil_c),
        "CRITICAL": s >= seuil_c,
    }.items():
        niveaux[nom_niv] = {
            "part_des_sessions": round(float(masque.mean()), 3),
            "taux_panne_24h_observe": round(float(yv[masque].mean()), 3) if masque.any() else None,
        }
    alerte = s >= seuil_w
    lecture = {
        "seuil_warning": seuil_w,
        "seuil_critical": seuil_c,
        "frequence_de_base": round(float(yv.mean()), 3),
        "niveaux": niveaux,
        "rappel_alerte": round(float(yv[alerte].sum() / yv.sum()), 3),
        "precision_alerte": round(float(yv[alerte].mean()), 3) if alerte.any() else None,
    }
    print(f"  B · seuils {seuil_w}/{seuil_c} → {json.dumps(lecture['niveaux'], ensure_ascii=False)}")
    print(f"  B · rappel alerte={lecture['rappel_alerte']}  précision alerte={lecture['precision_alerte']}")

    modele = candidats_B()[retenu].fit(X, y)
    joblib.dump(modele, MODELS_DIR / "usine_B_risque.joblib")

    meta = {
        "usine": "Usine_B",
        "type": "classification_binaire",
        "cible": f"Au moins une panne thermique dans les {HORIZON_B} prochaines sessions (24 h)",
        "algorithme": retenu,
        "features": FEATURES_B,
        "horizon_sessions": HORIZON_B,
        "n_sessions_entrainement": int(len(X)),
        "validation": f"TimeSeriesSplit walk-forward, {N_SPLITS} plis, gap de {HORIZON_B} sessions",
        "metriques_cv": resultats[retenu],
        "lecture_metier_des_seuils": lecture,
        "benchmark": resultats,
        "limite_connue": (
            "Les pannes simulées suivent un processus aléatoire dont seul le taux dépend "
            "du régime thermique : le modèle estime un NIVEAU DE RISQUE, il ne peut pas "
            "annoncer l'instant exact d'une panne. Recalibrage indispensable sur données terrain."
        ),
    }
    return meta


# ═════════════════════════════════════════════════════════════

def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print("── Usine A · RUL outil ──")
    meta_A = entrainer_usine_A()
    print("── Usine B · risque thermique 24 h ──")
    meta_B = entrainer_usine_B()

    commun = {
        "date_entrainement": datetime.now().isoformat(timespec="seconds"),
        "scikit_learn": sklearn.__version__,
    }
    for nom, meta in (("usine_A_rul", meta_A), ("usine_B_risque", meta_B)):
        meta.update(commun)
        (MODELS_DIR / f"{nom}_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPORTS_DIR / "benchmark_841.json").write_text(
        json.dumps({"usine_A": meta_A, "usine_B": meta_B}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"\nRetenus → A : {meta_A['algorithme']} · B : {meta_B['algorithme']}")
    print(f"Modèles : {MODELS_DIR}\nRapport : {REPORTS_DIR / 'benchmark_841.json'}")


if __name__ == "__main__":
    main()
