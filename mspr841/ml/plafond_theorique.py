"""
plafond_theorique.py — Jusqu'où un modèle peut-il aller sur ces données ? (MSPR TPRE841)

Les données de MECHA sont simulées : la loi qui génère les pannes est connue
(notebooks/02_gold_usine_A.ipynb et 03_gold_usine_B.ipynb). On peut donc calculer
la performance du MEILLEUR prédicteur possible, celui qui connaîtrait cette loi,
et la comparer à celle des modèles retenus. C'est ce « plafond » qui dit s'il
reste une marge de progression ou si l'erreur restante est du hasard pur.

  Usine B : un « oracle » calcule, pour chaque session, la vraie probabilité
            qu'au moins une panne thermique survienne dans les 24 h, à partir
            de la loi de simulation d'ORIGINE (régime thermique seul). Il est
            évalué sur les mêmes plis que les modèles. Les signes avant-coureurs
            ajoutés par enrichir_usine_B.py permettent au modèle de le dépasser.
  Usine A : on rejoue la loi d'usure de l'outil un grand nombre de fois et on
            mesure l'erreur du meilleur prédicteur de la durée de vie restante
            connaissant l'usure (son espérance conditionnelle).

Lancement (depuis la racine du dépôt), après train_models.py :
    python mspr841/ml/plafond_theorique.py

Sortie : reports/plafond_841.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mspr841" / "ml"))

import train_models as T  # noqa: E402

# ── Constantes de simulation, reprises des notebooks Gold ────
# Usine B (notebooks/03_gold_usine_B.ipynb)
B_PERIODE = 45 * 48          # période du cycle thermique, en sessions
B_LAMBDA_BASE = 0.0115       # taux de panne de base par session
B_AMPLITUDE = 0.85           # modulation du taux par le cycle
B_OFFSET = 11.5              # delta thermique nominal (K)
B_DEMI_AMPLITUDE = 2.5       # amplitude du cycle du delta (K)
B_BRUIT = 0.5                # écart-type du bruit de mesure (K)
B_SEUIL_HDF = 8.6            # sous ce delta, le taux de panne est triplé
# Usine A (notebooks/02_gold_usine_A.ipynb)
A_DUREE_VIE = 250
A_SEUIL_REMPLACEMENT = 0.90
A_INCREMENTS = {"REF01": (2.0, 3.0), "REF02": (2.5, 3.5), "REF03": (3.5, 5.0), "REF04": (2.0, 4.0)}
A_POIDS = [0.40, 0.30, 0.20, 0.10]
A_NB_VIES_SIMULEES = 20_000


def plafond_usine_B() -> dict:
    X, y = T.preparer_usine_B()
    n_total = len(X) + T.HORIZON_B
    t = np.arange(n_total)
    cycle = np.sin(2 * np.pi * t / B_PERIODE)

    # Taux de panne attendu à chaque session, bruit de mesure futur inconnu :
    # le facteur ×3 s'applique avec la probabilité que le delta passe sous le seuil.
    loi = NormalDist()
    delta_moyen = B_OFFSET - B_DEMI_AMPLITUDE * cycle
    p_sous_seuil = np.array([loi.cdf((B_SEUIL_HDF - m) / B_BRUIT) for m in delta_moyen])
    p_panne = np.clip(B_LAMBDA_BASE * (1 + B_AMPLITUDE * cycle) * (1 + 2 * p_sous_seuil), 0, 0.5)

    # Probabilité d'au moins une panne dans les HORIZON_B sessions suivantes.
    log_survie = np.concatenate([[0.0], np.cumsum(np.log1p(-p_panne))])
    idx = np.arange(len(X))
    oracle = 1 - np.exp(log_survie[idx + 1 + T.HORIZON_B] - log_survie[idx + 1])

    auc, ap, brier = [], [], []
    for _, te in TimeSeriesSplit(T.N_SPLITS, gap=T.HORIZON_B).split(X):
        auc.append(roc_auc_score(y.iloc[te], oracle[te]))
        ap.append(average_precision_score(y.iloc[te], oracle[te]))
        brier.append(brier_score_loss(y.iloc[te], oracle[te]))
    return {
        "ROC_AUC": round(float(np.mean(auc)), 3),
        "ROC_AUC_ecart_type": round(float(np.std(auc)), 3),
        "PR_AUC": round(float(np.mean(ap)), 3),
        "Brier": round(float(np.mean(brier)), 4),
    }


def plafond_usine_A(seed: int = T.SEED) -> dict:
    rng = np.random.default_rng(seed)
    bornes = np.array(list(A_INCREMENTS.values()))
    limite = A_DUREE_VIE * A_SEUIL_REMPLACEMENT
    usures, ruls = [], []
    for _ in range(A_NB_VIES_SIMULEES):
        usure, trajectoire = 0.0, []
        while True:
            lo, hi = bornes[rng.choice(len(bornes), p=A_POIDS)]
            usure += rng.uniform(lo, hi)
            if usure >= limite:
                break
            trajectoire.append(usure)
        n = len(trajectoire)
        usures.extend(trajectoire)
        ruls.extend(range(n, 0, -1))   # sessions restantes avant le remplacement
    df = pd.DataFrame({"usure": np.round(usures, 0), "rul": ruls})
    # Meilleur prédicteur possible connaissant l'usure : la médiane conditionnelle
    # minimise l'erreur absolue ; la moyenne conditionnelle minimise l'erreur quadratique.
    mediane = df.groupby("usure")["rul"].transform("median")
    moyenne = df.groupby("usure")["rul"].transform("mean")
    return {
        "MAE": round(float((df["rul"] - mediane).abs().mean()), 3),
        "RMSE": round(float(np.sqrt(((df["rul"] - moyenne) ** 2).mean())), 3),
        "vies_d_outil_simulees": A_NB_VIES_SIMULEES,
    }


def main() -> None:
    benchmark = json.loads((T.REPORTS_DIR / "benchmark_841.json").read_text(encoding="utf-8"))
    modele_A = benchmark["usine_A"]["metriques_cv"]
    modele_B = benchmark["usine_B"]["metriques_cv"]
    plafond_A = plafond_usine_A()
    plafond_B = plafond_usine_B()

    rapport = {
        "usine_A": {
            "modele_retenu": benchmark["usine_A"]["algorithme"],
            "modele": {"MAE": modele_A["MAE"], "RMSE": modele_A["RMSE"]},
            "plafond_theorique": plafond_A,
            "lecture": (
                "L'erreur du modèle est au niveau de l'erreur incompressible de la simulation "
                "(l'écart entre les deux tient à l'échantillon) : "
                "le nombre de sessions restantes dépend des pièces qui seront usinées, "
                "tirées au hasard. Aucun modèle ne peut faire mieux sur ces données."
            ),
        },
        "usine_B": {
            "modele_retenu": benchmark["usine_B"]["algorithme"],
            "modele": {k: modele_B[k] for k in ("ROC_AUC", "PR_AUC", "Brier")},
            "plafond_du_regime_thermique_seul": plafond_B,
            "gain_des_signes_avant_coureurs": {
                "ROC_AUC": round(modele_B["ROC_AUC"] - plafond_B["ROC_AUC"], 3),
                "PR_AUC": round(modele_B["PR_AUC"] - plafond_B["PR_AUC"], 3),
            },
            "lecture": (
                "Le plafond ci-dessus est celui d'un prédicteur qui connaîtrait la loi de "
                "simulation d'origine, où l'instant des pannes est tiré au hasard et où seul "
                "leur taux dépend du régime thermique. Depuis l'ajout de signes avant-coureurs "
                "(enrichir_usine_B.py), le modèle dépasse ce plafond : l'écart mesure ce "
                "qu'apporte la dérive du delta avant la panne."
            ),
        },
    }
    sortie = T.REPORTS_DIR / "plafond_841.json"
    sortie.write_text(json.dumps(rapport, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Usine A · modèle MAE={modele_A['MAE']}  ·  plafond MAE={plafond_A['MAE']}")
    print(f"Usine B · modèle AUC={modele_B['ROC_AUC']}  ·  plafond du régime seul AUC={plafond_B['ROC_AUC']}")
    print(f"Rapport : {sortie}")


if __name__ == "__main__":
    main()
