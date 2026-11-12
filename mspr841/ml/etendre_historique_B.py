"""
etendre_historique_B.py : historique d'entraînement étendu pour l'usine B (MSPR TPRE841)

Constat : six mois d'historique, c'est 111 pannes thermiques et quatre cycles
thermiques seulement. C'est peu pour comparer des modèles : les ensembles
d'arbres sur-apprennent et les scores varient beaucoup d'un pli à l'autre.

Ce script prolonge la simulation de l'usine B du 29/06/2024 jusqu'à DATE_FIN,
avec exactement les mêmes règles que les six premiers mois :
  - loi d'origine (notebooks/03_gold_usine_B.ipynb) : delta thermique
    sinusoïdal + bruit ; pannes tirées selon un taux qui suit le même cycle,
    multiplié par 3 sous 8,6 K ;
  - signes avant-coureurs (enrichir_usine_B.py) : dérive avant 80 % des
    pannes, pannes sans signe, dérives sans panne.

Les six premiers mois ne sont pas modifiés : ce sont ceux de usine_B.parquet,
que les tableaux de bord rejouent. Seul l'entraînement utilise le fichier étendu.

Lancement (depuis la racine du dépôt), après enrichir_usine_B.py :
    python mspr841/ml/etendre_historique_B.py

Sortie : data/gold/usine_B_historique.parquet
         data/gold/extension_usine_B.json (bilan)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import enrichir_usine_B as E

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
SORTIE = GOLD / "usine_B_historique.parquet"
JOURNAL = GOLD / "extension_usine_B.json"

# Date fixe et non « aujourd'hui » : le fichier doit être reproductible.
DATE_FIN = "2026-11-12 06:00"
SEED = 2026

# Loi d'origine, reprise de notebooks/03_gold_usine_B.ipynb
PERIODE = 45 * 48
OFFSET_THERMIQUE = 11.5
DEMI_AMPLITUDE = 2.5
BRUIT = 0.5
LAMBDA_BASE = 0.0115
AMPLITUDE = 0.85
SEUIL_DELTA_HDF = 8.6


def main() -> None:
    gold = pd.read_parquet(GOLD / "usine_B.parquet").sort_values("timestamp").reset_index(drop=True)
    base = gold[["timestamp", "temp_process_delta", "panne_thermique"]].copy()
    base["origine"] = "gold"
    n0 = len(base)

    debut = base["timestamp"].iloc[-1] + pd.Timedelta(minutes=30)
    horodatage = pd.date_range(debut, pd.Timestamp(DATE_FIN), freq="30min")
    n = len(horodatage)
    rng = np.random.default_rng(SEED)

    # Même loi que le notebook Gold ; l'indice continue celui des six premiers mois,
    # donc le cycle thermique se poursuit sans rupture de phase.
    t = np.arange(n0, n0 + n)
    cycle = np.sin(2 * np.pi * t / PERIODE)
    delta = OFFSET_THERMIQUE - DEMI_AMPLITUDE * cycle + rng.normal(0, BRUIT, n)
    taux = LAMBDA_BASE * (1 + AMPLITUDE * cycle)
    proba = (taux * np.where(delta < SEUIL_DELTA_HDF, 3.0, 1.0)).clip(0, 0.5)
    panne = (rng.random(n) < proba).astype(int)

    # Signes avant-coureurs : mêmes règles que pour les six premiers mois.
    pannes = np.flatnonzero(panne == 1)
    baisse, annoncees, fausses = E.calculer_baisse(n, pannes, rng)
    delta = np.round(np.maximum(delta - baisse, E.DELTA_MIN), 2)

    extension = pd.DataFrame({
        "timestamp": horodatage,
        "temp_process_delta": delta,
        "panne_thermique": panne,
        "origine": "simulation_etendue",
    })
    complet = pd.concat([base, extension], ignore_index=True)
    complet["timestamp"] = complet["timestamp"].astype("datetime64[us]")
    complet.to_parquet(SORTIE, index=False)

    journal = {
        "source": "usine_B.parquet",
        "graine": SEED,
        "periode": [str(complet["timestamp"].iloc[0]), str(complet["timestamp"].iloc[-1])],
        "sessions_gold": int(n0),
        "sessions_simulees": int(n),
        "sessions_total": int(len(complet)),
        "pannes_thermiques_gold": int(base["panne_thermique"].sum()),
        "pannes_thermiques_simulees": int(panne.sum()),
        "pannes_thermiques_total": int(complet["panne_thermique"].sum()),
        "pannes_annoncees_dans_l_extension": int(len(annoncees)),
        "derives_sans_panne_dans_l_extension": int(len(fausses)),
        "taux_de_panne_gold": round(float(base["panne_thermique"].mean()), 4),
        "taux_de_panne_extension": round(float(panne.mean()), 4),
        "delta_moyen_gold": round(float(base["temp_process_delta"].mean()), 3),
        "delta_moyen_extension": round(float(delta.mean()), 3),
    }
    JOURNAL.write_text(json.dumps(journal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(journal, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
