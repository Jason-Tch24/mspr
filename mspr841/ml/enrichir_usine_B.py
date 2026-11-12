"""
enrichir_usine_B.py — Ajout de signes avant-coureurs aux pannes thermiques (MSPR TPRE841)

Constat (mspr841/ml/plafond_theorique.py) : dans la simulation d'origine, l'instant
d'une panne thermique est tiré au hasard ; seul son taux dépend du régime thermique.
Aucun modèle ne peut alors dépasser une ROC-AUC d'environ 0,75.

Sur une machine réelle, une panne thermique est le plus souvent précédée d'une
DÉGRADATION PROGRESSIVE : le circuit de refroidissement s'encrasse, le delta
process/air baisse pendant plusieurs heures, puis la machine s'arrête. Le sujet
autorise à enrichir les données pour « intégrer des événements de panne ou de
dégradation progressive ». C'est ce que fait ce script.

Hypothèses de simulation ajoutées (les pannes elles-mêmes ne changent pas) :
  H1. 80 % des pannes thermiques sont précédées d'une dérive : le delta baisse
      progressivement de 1,2 à 2,5 K pendant les 12 à 36 h qui précèdent la panne.
      Les 20 % restants surviennent sans prévenir (casse brutale).
  H2. Après la panne, l'intervention rétablit le delta en 3 h environ.
  H3. Des dérives SANS panne sont ajoutées (une pour quatre pannes) : le delta
      baisse puis revient seul à la normale. Elles produiront des fausses alertes,
      comme sur le terrain.
  H4. Les indicateurs qui dépendent du delta sont recalculés avec les formules du
      notebook Gold : température process, taux de rebut, stabilité, qualité, TRS.
      Les limites de contrôle statistique sont recalculées de la même façon.

Le fichier d'origine est conservé (usine_B_base.parquet) ; le script repart
toujours de lui : le relancer redonne exactement le même résultat (graine fixée).

Lancement (depuis la racine du dépôt) :
    python mspr841/ml/enrichir_usine_B.py
    python mspr841/ml/train_models.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
FICHIER = GOLD / "usine_B.parquet"
BASE = GOLD / "usine_B_base.parquet"
LIMITES = GOLD / "limites_usine_B.json"
JOURNAL = GOLD / "enrichissement_usine_B.json"

SEED = 841
PART_PANNES_ANNONCEES = 0.80          # H1
DUREE_DERIVE = (24, 72)               # sessions de 30 min → 12 à 36 h
AMPLITUDE_DERIVE = (1.2, 2.5)         # K
DUREE_RETOUR = 6                      # H2 : sessions → 3 h
RATIO_FAUSSES_DERIVES = 0.25          # H3
DELTA_MIN = 6.5                       # plancher physique du delta (K)
SEUIL_DELTA_HDF = 8.6                 # repris du notebook 03_gold_usine_B
FIN_PERIODE_REFERENCE = "2024-02-01"  # période de référence des limites SPC


def _appliquer_derive(baisse: np.ndarray, fin: int, duree: int, amplitude: float, retour: int) -> None:
    """Baisse progressive jusqu'à `fin` (inclus), puis retour linéaire à zéro."""
    n = len(baisse)
    debut = max(0, fin - duree + 1)
    k = np.arange(debut, fin + 1)
    # Rampe convexe : la dégradation s'accélère à l'approche de la panne.
    rampe = amplitude * ((k - debut + 1) / (fin - debut + 1)) ** 1.5
    baisse[k] = np.maximum(baisse[k], rampe)
    k2 = np.arange(fin + 1, min(n, fin + 1 + retour))
    if len(k2):
        baisse[k2] = np.maximum(baisse[k2], amplitude * (1 - (k2 - fin) / (retour + 1)))


def _limites(serie: pd.Series, nom: str, n_sigma: int = 3) -> dict:
    mu, sigma = float(serie.mean()), float(serie.std())
    return {
        "kpi": nom,
        "moyenne": round(mu, 4),
        "sigma": round(sigma, 4),
        "ucl": round(mu + n_sigma * sigma, 4),
        "lcl": round(max(mu - n_sigma * sigma, 0), 4),
        "uwl": round(mu + 2 * sigma, 4),
        "lwl": round(max(mu - 2 * sigma, 0), 4),
    }


def calculer_baisse(n: int, pannes: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Baisse du delta (en K) à appliquer à chaque session, selon H1 à H3.
    Renvoie (baisse, pannes annoncées, positions des dérives sans panne).
    Utilisée ici et par etendre_historique_B.py : mêmes règles partout.
    """
    # H1, H2 : dérive avant les pannes annoncées
    baisse = np.zeros(n)
    annoncees = pannes[rng.random(len(pannes)) < PART_PANNES_ANNONCEES]
    for i in annoncees:
        _appliquer_derive(
            baisse, fin=int(i),
            duree=int(rng.integers(DUREE_DERIVE[0], DUREE_DERIVE[1] + 1)),
            amplitude=float(rng.uniform(*AMPLITUDE_DERIVE)),
            retour=DUREE_RETOUR,
        )

    # H3 : dérives sans panne, loin de toute panne thermique
    nb_fausses = int(round(len(pannes) * RATIO_FAUSSES_DERIVES))
    loin = np.ones(n, dtype=bool)
    for i in pannes:
        loin[max(0, i - 96):min(n, i + 48)] = False
    candidats = np.flatnonzero(loin[DUREE_DERIVE[1]:]) + DUREE_DERIVE[1]
    fausses = np.sort(rng.choice(candidats, size=min(nb_fausses, len(candidats)), replace=False))
    for i in fausses:
        duree = int(rng.integers(DUREE_DERIVE[0], DUREE_DERIVE[1] + 1))
        _appliquer_derive(
            baisse, fin=int(i), duree=duree,
            amplitude=float(rng.uniform(*AMPLITUDE_DERIVE)) * 0.8,
            retour=duree // 2,
        )
    return baisse, annoncees, fausses


def main() -> None:
    if not BASE.exists():
        shutil.copyfile(FICHIER, BASE)
    df = pd.read_parquet(BASE).sort_values("timestamp").reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    n = len(df)
    ancien = df["temp_process_delta"].to_numpy(dtype=float)
    pannes = np.flatnonzero(df["panne_thermique"].to_numpy() == 1)
    baisse, annoncees, fausses = calculer_baisse(n, pannes, rng)

    nouveau = np.round(np.maximum(ancien - baisse, DELTA_MIN), 2)
    df["temp_process_delta"] = nouveau
    df["temp_process_c"] = np.round(df["temp_air_c"] + df["temp_process_delta"], 2)

    # ── H4 : indicateurs dépendant du delta (formules du notebook Gold) ─
    ecart = np.maximum(0, SEUIL_DELTA_HDF - nouveau) - np.maximum(0, SEUIL_DELTA_HDF - ancien)
    df["taux_rebut"] = np.round((df["taux_rebut"] + 0.05 * ecart).clip(0, 1), 4)
    df["indice_stabilite_process"] = np.round((df["indice_stabilite_process"] - 0.05 * ecart).clip(0, 1), 4)
    df["qualite"] = np.round(1 - df["taux_rebut"], 4)
    df["TRS"] = np.round(df["disponibilite"] * df["performance"] * df["qualite"], 4)
    df["TRS_7j"] = df["TRS"].rolling(336, min_periods=1).mean()
    df["delta_ma"] = df["temp_process_delta"].rolling(100, min_periods=1).mean()
    df.to_parquet(FICHIER, index=False)

    # ── Limites de contrôle statistique (même méthode que le notebook) ─
    ref = df[(df["timestamp"] < FIN_PERIODE_REFERENCE) & (df["panne_machine"] == 0)]
    limites = {
        "TRS": _limites(ref["TRS"], "TRS"),
        "taux_rebut": _limites(ref["taux_rebut"], "taux_rebut"),
        "temps_cycle_min": _limites(ref["temps_cycle_min"], "temps_cycle_min"),
        "temp_process_delta": _limites(ref["temp_process_delta"], "temp_process_delta"),
        "consommation_kwh": _limites(ref["consommation_kwh"], "consommation_kwh"),
        "indice_stabilite": _limites(ref["indice_stabilite_process"], "indice_stabilite"),
    }
    LIMITES.write_text(json.dumps(limites, indent=2) + "\n", encoding="utf-8")

    journal = {
        "source": BASE.name,
        "graine": SEED,
        "pannes_thermiques": int(len(pannes)),
        "pannes_annoncees_par_une_derive": int(len(annoncees)),
        "pannes_sans_signe_avant_coureur": int(len(pannes) - len(annoncees)),
        "derives_sans_panne": int(len(fausses)),
        "sessions_modifiees": int((baisse > 0).sum()),
        "part_des_sessions_modifiees": round(float((baisse > 0).mean()), 3),
        "delta_moyen_avant": round(float(ancien.mean()), 3),
        "delta_moyen_apres": round(float(nouveau.mean()), 3),
        "hypotheses": {
            "H1": f"{PART_PANNES_ANNONCEES:.0%} des pannes précédées d'une baisse de "
                  f"{AMPLITUDE_DERIVE[0]} à {AMPLITUDE_DERIVE[1]} K sur {DUREE_DERIVE[0]} à {DUREE_DERIVE[1]} sessions",
            "H2": f"retour à la normale en {DUREE_RETOUR} sessions après la panne",
            "H3": f"une dérive sans panne pour {int(1 / RATIO_FAUSSES_DERIVES)} pannes",
            "H4": "rebut, stabilité, qualité, TRS et limites SPC recalculés",
        },
    }
    JOURNAL.write_text(json.dumps(journal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in journal.items() if k != "hypotheses"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
