"""
etendre_historique_AC.py : historiques étendus des usines A et C (MSPR TPRE841)

Même principe que etendre_historique_B.py : la simulation de chaque usine est
prolongée du 29/06/2024 jusqu'à DATE_FIN avec les règles de son notebook Gold
(notebooks/02_gold_usine_A.ipynb et 04_gold_usine_C.ipynb). L'usure de l'outil
reprend là où les six premiers mois s'arrêtent : pas de rupture à la jonction.

Les six premiers mois ne sont pas modifiés : ce sont ceux que les tableaux de
bord rejouent. Les fichiers étendus ne servent qu'à l'entraînement et à
l'analyse.

Lancement (depuis la racine du dépôt) :
    python mspr841/ml/etendre_historique_AC.py

Sorties : data/gold/usine_A_historique.parquet
          data/gold/usine_C_historique.parquet
          data/gold/extension_usines_A_C.json (bilan)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
JOURNAL = GOLD / "extension_usines_A_C.json"

DATE_FIN = "2026-11-12 06:00"      # même date fixe que pour l'usine B
DUREE_VIE_OUTIL = 250
TYPES_PIECES = ["REF01", "REF02", "REF03", "REF04"]

# Règles reprises des notebooks Gold, une entrée par usine.
REGLES = {
    "A": {
        "graine": 2042,
        "puissance_w": 6283.0, "couple_nominal": 40.0, "sigma_couple": 6.0, "bornes_couple": (20, 65),
        "bornes_vitesse": (1200, 1800),
        "poids_pieces": [0.40, 0.30, 0.20, 0.10],
        "increments": {"REF01": (2.0, 3.0), "REF02": (2.5, 3.5), "REF03": (3.5, 5.0), "REF04": (2.0, 4.0)},
        "seuil_remplacement": 0.90,
        "coef_panne_usure": 0.15, "p_surcharge": 0.005, "p_aleatoire": 0.001,
        "coef_cycle": 0.003, "sigma_cycle": 1.5, "sigma_conso": 0.4,
    },
    "C": {
        "graine": 2256,
        "puissance_w": 5800.0, "couple_nominal": 38.0, "sigma_couple": 5.0, "bornes_couple": (20, 60),
        "bornes_vitesse": (900, 1800),
        "poids_pieces": [0.25, 0.25, 0.35, 0.15],
        "increments": {"REF01": (2.0, 3.0), "REF02": (2.5, 3.5), "REF03": (4.0, 5.5), "REF04": (2.5, 4.0)},
        "seuil_remplacement": 0.82,
        "coef_panne_usure": 0.06, "p_surcharge": 0.002, "p_aleatoire": 0.001,
        "coef_cycle": 0.001, "sigma_cycle": 2.0, "sigma_conso": 0.35,
        # Propre à l'usine C : instabilité du process selon la pièce et l'équipe
        "ecart_vitesse": {"REF01": (0, 50), "REF02": (-20, 55), "REF03": (-80, 60), "REF04": (-40, 55)},
        "rebut_par_piece": {"REF01": 0.03, "REF02": 0.05, "REF03": 0.12, "REF04": 0.07},
        "facteur_equipe": {"Matin": 1.00, "Apres-midi": 1.10, "Nuit": 1.35},
        "isp_par_piece": {"REF01": 0.92, "REF02": 0.85, "REF03": 0.62, "REF04": 0.78},
        "facteur_isp_equipe": {"Matin": 1.00, "Apres-midi": 0.97, "Nuit": 0.88},
    },
}

COLONNES = [
    "timestamp", "type_piece", "equipe", "vitesse_rotation_rpm", "couple_nm",
    "usure_outil_min", "remplacement_outil", "usure_cumulee_pct",
    "panne_machine", "panne_usure_outil", "panne_thermique", "panne_surcharge", "panne_aleatoire",
    "temps_cycle_min", "derive_cycle_pct", "taux_rebut", "indice_stabilite_process",
    "consommation_kwh", "disponibilite", "performance", "qualite", "TRS",
]


def _equipe(heures: np.ndarray) -> np.ndarray:
    return np.where((heures >= 6) & (heures < 14), "Matin",
                    np.where((heures >= 14) & (heures < 22), "Apres-midi", "Nuit"))


def simuler(usine: str, horodatage: pd.DatetimeIndex, usure_initiale: float) -> pd.DataFrame:
    r = REGLES[usine]
    rng = np.random.default_rng(r["graine"])
    n = len(horodatage)
    vitesse_nominale = round((r["puissance_w"] * 60) / (2 * np.pi * r["couple_nominal"]))
    temps_cycle_nominal = round(60_000 / vitesse_nominale, 2)

    df = pd.DataFrame({"timestamp": horodatage})
    df["type_piece"] = rng.choice(TYPES_PIECES, size=n, p=r["poids_pieces"])
    df["equipe"] = _equipe(horodatage.hour.to_numpy())
    piece = df["type_piece"].to_numpy()

    # Vitesse et couple
    if usine == "C":
        ecart = np.array([r["ecart_vitesse"][p][0] for p in piece])
        sigma = np.array([r["ecart_vitesse"][p][1] for p in piece])
        vitesse = rng.normal(vitesse_nominale + ecart, sigma)
    else:
        vitesse = rng.normal(vitesse_nominale, 60, n)
    df["vitesse_rotation_rpm"] = np.clip(vitesse.astype(int), *r["bornes_vitesse"])
    df["couple_nm"] = np.round(np.clip(rng.normal(r["couple_nominal"], r["sigma_couple"], n), *r["bornes_couple"]), 2)

    # Usure de l'outil : incrément selon la pièce, remplacement au seuil
    bas = np.array([r["increments"][p][0] for p in piece])
    haut = np.array([r["increments"][p][1] for p in piece])
    increments = rng.uniform(bas, haut)
    limite = DUREE_VIE_OUTIL * r["seuil_remplacement"]
    usure, remplacement = np.empty(n), np.zeros(n, dtype=int)
    courante = usure_initiale
    for i in range(n):
        courante += increments[i]
        if courante >= limite:
            remplacement[i] = 1
            courante = 0.0
        usure[i] = round(courante, 1)
    df["usure_outil_min"] = usure
    df["remplacement_outil"] = remplacement
    df["usure_cumulee_pct"] = np.round(np.clip(usure / DUREE_VIE_OUTIL * 100, 0, 100), 2)

    # Stabilité du process (usine C : dépend de la pièce et de l'équipe)
    if usine == "C":
        base = np.array([r["isp_par_piece"][p] for p in piece])
        facteur = np.array([r["facteur_isp_equipe"][e] for e in df["equipe"]])
        stabilite = np.round(np.clip(base * facteur + rng.normal(0, 0.04, n), 0, 1), 4)

    # Pannes
    prob_usure = (df["usure_cumulee_pct"] / 100) ** 2 * r["coef_panne_usure"]
    panne_usure = ((rng.random(n) < prob_usure) & (df["usure_cumulee_pct"] > 70)).astype(int)
    if usine == "C":
        panne_process = (rng.random(n) < np.where(stabilite < 0.55, 0.08, 0.01)).astype(int)
    else:
        panne_process = np.zeros(n, dtype=int)
    panne_surcharge = (rng.random(n) < r["p_surcharge"]).astype(int)
    panne_aleatoire = (rng.random(n) < r["p_aleatoire"]).astype(int)
    panne = ((panne_usure == 1) | (panne_process == 1) | (panne_surcharge == 1) | (panne_aleatoire == 1)).astype(int)
    df["panne_machine"] = panne
    df["panne_usure_outil"] = panne_usure
    df["panne_thermique"] = panne_process
    df["panne_surcharge"] = panne_surcharge
    df["panne_aleatoire"] = panne_aleatoire

    # Indicateurs
    df["temps_cycle_min"] = np.round(np.clip(
        temps_cycle_nominal * (1 + r["coef_cycle"] * df["usure_cumulee_pct"]) + rng.normal(0, r["sigma_cycle"], n),
        20, None), 2)
    df["derive_cycle_pct"] = np.round((df["temps_cycle_min"] - temps_cycle_nominal) / temps_cycle_nominal * 100, 2)
    if usine == "C":
        base = np.array([r["rebut_par_piece"][p] for p in piece])
        facteur = np.array([r["facteur_equipe"][e] for e in df["equipe"]])
        df["taux_rebut"] = np.round(np.clip(base * facteur * (2 - stabilite) + rng.normal(0, 0.008, n), 0, 1), 4)
        df["indice_stabilite_process"] = stabilite
    else:
        df["taux_rebut"] = np.round(np.clip(
            0.02 + 0.0003 * (df["usure_outil_min"] ** 2) / DUREE_VIE_OUTIL + 0.15 * panne + rng.normal(0, 0.004, n),
            0, 1), 4)
        df["indice_stabilite_process"] = np.round(np.clip(
            0.92 - 0.30 * panne - 0.001 * df["usure_cumulee_pct"] + rng.normal(0, 0.03, n), 0, 1), 4)
    df["consommation_kwh"] = np.round(np.clip(
        (df["vitesse_rotation_rpm"] * df["couple_nm"]) / 9550 * 0.5 + rng.normal(0, r["sigma_conso"], n), 0, None), 2)
    df["disponibilite"] = (panne == 0).astype(float)
    df["performance"] = np.round(np.clip(df["vitesse_rotation_rpm"] / vitesse_nominale, None, 1.0), 4)
    df["qualite"] = np.round(1 - df["taux_rebut"], 4)
    df["TRS"] = np.round(df["disponibilite"] * df["performance"] * df["qualite"], 4)
    return df[COLONNES]


def main() -> None:
    journal = {}
    for usine in ("A", "C"):
        gold = pd.read_parquet(GOLD / f"usine_{usine}.parquet").sort_values("timestamp").reset_index(drop=True)
        base = gold[COLONNES].copy()
        base["origine"] = "gold"
        debut = base["timestamp"].iloc[-1] + pd.Timedelta(minutes=30)
        horodatage = pd.date_range(debut, pd.Timestamp(DATE_FIN), freq="30min")
        extension = simuler(usine, horodatage, usure_initiale=float(base["usure_outil_min"].iloc[-1]))
        extension["origine"] = "simulation_etendue"
        complet = pd.concat([base, extension], ignore_index=True)
        complet["timestamp"] = complet["timestamp"].astype("datetime64[us]")
        complet.to_parquet(GOLD / f"usine_{usine}_historique.parquet", index=False)

        def resume(d: pd.DataFrame) -> dict:
            return {
                "sessions": int(len(d)),
                "remplacements_outil": int(d["remplacement_outil"].sum()),
                "taux_de_panne": round(float(d["panne_machine"].mean()), 4),
                "taux_rebut_moyen": round(float(d["taux_rebut"].mean()), 4),
                "TRS_moyen": round(float(d["TRS"].mean()), 4),
                "temps_cycle_moyen": round(float(d["temps_cycle_min"].mean()), 2),
                "usure_moyenne_pct": round(float(d["usure_cumulee_pct"].mean()), 2),
            }
        journal[f"usine_{usine}"] = {
            "graine": REGLES[usine]["graine"],
            "periode": [str(complet["timestamp"].iloc[0]), str(complet["timestamp"].iloc[-1])],
            "gold": resume(base),
            "extension": resume(extension),
            "total": resume(complet),
        }
    JOURNAL.write_text(json.dumps(journal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(journal, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
