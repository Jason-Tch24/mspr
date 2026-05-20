# ============================================================
# kpi_engine.py — Moteur de calcul des KPIs agrégés MECHA
#
# DÉCISION ARCHITECTURALE :
# Le dashboard ne calcule jamais. Il lit des résultats pré-calculés.
# kpi_engine est le seul responsable des agrégations fenêtrées,
# des statuts machines, et du statut global par usine.
#
# APPELÉ PAR : simulator.py à chaque tick
# LIT DEPUIS : store.BUFFER_24H, store.CURRENT_STATE
# ÉCRIT DANS : store.AGGREGATIONS, store.MACHINE_STATE,
#              store.CURRENT_STATE (statut_global + nb_alertes)
# ============================================================

import pandas as pd
import numpy as np
from datetime import datetime

import store
from config import (
    USINES, MACHINES,
    SESSION_DURATION_MIN,
    TRS_SEUIL_ACCEPTABLE, TRS_SEUIL_CRITIQUE,
    REBUT_SEUIL_ACCEPTABLE,
    USURE_SEUIL_WARNING, USURE_SEUIL_CRITIQUE,
)

# ─────────────────────────────────────────────────────────────
# TAILLES DE FENÊTRES EN NOMBRE DE SESSIONS
# 1 session = SESSION_DURATION_MIN minutes (30 min)
# 1h  = 60  / 30 = 2  sessions (trop petit, on prend 1h = 2 sessions)
# 8h  = 480 / 30 = 16 sessions
# 24h = 1440/ 30 = 48 sessions
#
# DÉCISION : on utilise des fenêtres en sessions pour éviter
# de dépendre du timestamp (qui peut avoir des gaps si la
# simulation est pausée). Le calcul est plus robuste.
# ─────────────────────────────────────────────────────────────
_SESSIONS_PAR_HEURE = int(60 / SESSION_DURATION_MIN)   # 2

FENETRES = {
    '1h' : max(1, _SESSIONS_PAR_HEURE * 1),    # 2  sessions
    '8h' : max(1, _SESSIONS_PAR_HEURE * 8),    # 16 sessions
    '24h': max(1, _SESSIONS_PAR_HEURE * 24),   # 48 sessions
}


# ─────────────────────────────────────────────────────────────
# CALCUL DES AGRÉGATIONS FENÊTRÉES
# ─────────────────────────────────────────────────────────────

def _calculer_agregations_fenetre(
    df: pd.DataFrame,
    n_sessions: int
) -> dict:
    """
    Calcule les métriques agrégées sur les N dernières sessions
    d'un buffer donné sous forme de DataFrame.

    Retourne un dict vide si le buffer est insuffisant.
    On ne calcule pas sur un buffer trop petit pour éviter
    des métriques non représentatives au démarrage.
    """
    if df.empty or len(df) == 0:
        return _agregation_vide()

    # Prendre les N dernières sessions disponibles
    # Si moins de N sessions dans le buffer, on prend tout
    fenetre_df = df.tail(n_sessions).copy()

    if len(fenetre_df) == 0:
        return _agregation_vide()

    # ── TRS ──────────────────────────────────────────────────
    trs_values = fenetre_df['TRS'].dropna()
    trs_moyen  = float(trs_values.mean()) if len(trs_values) > 0 else 0.0
    trs_min    = float(trs_values.min())  if len(trs_values) > 0 else 0.0
    trs_max    = float(trs_values.max())  if len(trs_values) > 0 else 0.0

    # ── Rebut ─────────────────────────────────────────────────
    rebut_values = fenetre_df['taux_rebut'].dropna()
    rebut_moyen  = float(rebut_values.mean()) if len(rebut_values) > 0 else 0.0
    rebut_max    = float(rebut_values.max())  if len(rebut_values) > 0 else 0.0

    # ── Composantes TRS ───────────────────────────────────────
    dispo_moy = float(fenetre_df['disponibilite'].mean()) \
        if 'disponibilite' in fenetre_df else 0.0
    perf_moy  = float(fenetre_df['performance'].mean()) \
        if 'performance' in fenetre_df else 0.0
    qual_moy  = float(fenetre_df['qualite'].mean()) \
        if 'qualite' in fenetre_df else 0.0

    # ── Pannes et interventions ───────────────────────────────
    nb_pannes = int(fenetre_df['panne_machine'].sum()) \
        if 'panne_machine' in fenetre_df else 0

    # ── Production ───────────────────────────────────────────
    pieces_prod   = int(fenetre_df['pieces_produites'].sum()) \
        if 'pieces_produites' in fenetre_df else 0
    pieces_rebut  = int(fenetre_df['pieces_rebutees'].sum()) \
        if 'pieces_rebutees' in fenetre_df else 0

    # ── Énergie ───────────────────────────────────────────────
    energie_totale = float(fenetre_df['consommation_kwh'].sum()) \
        if 'consommation_kwh' in fenetre_df else 0.0

    return {
        'TRS_moyen'        : round(trs_moyen, 4),
        'TRS_min'          : round(trs_min, 4),
        'TRS_max'          : round(trs_max, 4),
        'rebut_moyen'      : round(rebut_moyen, 4),
        'rebut_max'        : round(rebut_max, 4),
        'nb_pannes'        : nb_pannes,
        'nb_alertes'       : 0,  # mis à jour par _update_statut_global
        'energie_totale'   : round(energie_totale, 2),
        'pieces_produites' : pieces_prod,
        'pieces_rebutees'  : pieces_rebut,
        'disponibilite'    : round(dispo_moy, 4),
        'performance'      : round(perf_moy, 4),
        'qualite'          : round(qual_moy, 4),
        'nb_sessions'      : len(fenetre_df),
    }


def _agregation_vide() -> dict:
    """Retourne un dictionnaire d'agrégation avec toutes valeurs à zéro."""
    return {
        'TRS_moyen'        : 0.0,
        'TRS_min'          : 0.0,
        'TRS_max'          : 0.0,
        'rebut_moyen'      : 0.0,
        'rebut_max'        : 0.0,
        'nb_pannes'        : 0,
        'nb_alertes'       : 0,
        'energie_totale'   : 0.0,
        'pieces_produites' : 0,
        'pieces_rebutees'  : 0,
        'disponibilite'    : 0.0,
        'performance'      : 0.0,
        'qualite'          : 0.0,
        'nb_sessions'      : 0,
    }


# ─────────────────────────────────────────────────────────────
# CALCUL DU STATUT MACHINE
# ─────────────────────────────────────────────────────────────

def _calculer_machine_state(
    usine_id: str,
    state: dict
) -> None:
    """
    Détermine le statut opérationnel de la machine active
    dans la session courante et met à jour MACHINE_STATE.

    Une session concerne une seule machine à la fois.
    On met à jour uniquement la machine active dans cette session.
    Les autres machines gardent leur dernier état connu.
    """
    machine_id = state.get('machine_id')
    if not machine_id or machine_id not in MACHINES:
        return

    # Déterminer le statut
    if state.get('panne_machine', 0) == 1:
        if state.get('intervention_maintenance', 0) == 1:
            statut = 'MAINTENANCE'
        else:
            statut = 'ARRET'
    elif state.get('rupture_appro', 0) == 1:
        statut = 'STANDBY'
    else:
        statut = 'EN_PRODUCTION'

    # Mise à jour du statut machine dans le store
    store.update_machine_state(usine_id, machine_id, {
        'statut'          : statut,
        'usure_pct'       : state.get('usure_cumulee_pct', 0.0),
        'taux_rebut'      : state.get('taux_rebut', 0.0),
        'temps_cycle_min' : state.get('temps_cycle_min', 0.0),
        'derniere_panne'  : (
            state.get('type_panne')
            if state.get('panne_machine', 0) == 1 else None
        ),
    })


# ─────────────────────────────────────────────────────────────
# CALCUL DU STATUT GLOBAL USINE
# ─────────────────────────────────────────────────────────────

def _calculer_statut_global(usine_id: str, state: dict) -> str:
    """
    Calcule le statut global de l'usine à partir de :
      - la présence d'alertes CRITICAL actives
      - la présence d'alertes WARNING actives
      - le TRS courant par rapport aux seuils industriels
      - l'état de panne machine courante

    Retourne 'CRITICAL', 'WARNING' ou 'OK'.

    DÉCISION : le statut global est conservateur.
    Une seule alerte CRITICAL suffit à passer en CRITICAL.
    Une seule alerte WARNING suffit à passer en WARNING si pas CRITICAL.
    """
    # Lire les alertes actives pour cette usine
    alertes = store.get_active_alerts(usine_id)
    nb_alertes = len(alertes)

    if nb_alertes > 0:
        severites = alertes['severite'].tolist()
        if 'CRITICAL' in severites:
            return 'CRITICAL'
        if 'WARNING' in severites:
            return 'WARNING'

    # Vérification TRS même sans alerte active
    # (peut arriver au démarrage avant que l'alert_engine ait évalué)
    trs = state.get('TRS', 1.0)
    if trs < TRS_SEUIL_CRITIQUE:
        return 'CRITICAL'
    if trs < TRS_SEUIL_ACCEPTABLE:
        return 'WARNING'

    # Panne machine en cours
    if state.get('panne_machine', 0) == 1:
        return 'CRITICAL'

    return 'OK'


# ─────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────

def process_tick() -> None:
    """
    Traite un tick de simulation pour toutes les usines.
    Appelé par simulator._tick_loop() à chaque tick.

    Séquence pour chaque usine :
      1. Lire le buffer sous forme de DataFrame
      2. Calculer les agrégations sur 1h, 8h, 24h
      3. Mettre à jour AGGREGATIONS dans le store
      4. Calculer le statut de la machine active
      5. Mettre à jour MACHINE_STATE dans le store
      6. Calculer le statut global de l'usine
      7. Mettre à jour statut_global et nb_alertes dans CURRENT_STATE
    """
    for usine_id in USINES:

        # ── Lecture buffer ────────────────────────────────────
        df    = store.get_buffer_as_df(usine_id)
        state = store.get_current_state(usine_id)

        if df.empty:
            continue

        # ── Agrégations fenêtrées ─────────────────────────────
        aggs = {}
        for fenetre_label, n_sessions in FENETRES.items():
            aggs[fenetre_label] = _calculer_agregations_fenetre(
                df, n_sessions
            )

        # Injecter le nombre d'alertes actives dans l'agrégation 1h
        # pour cohérence avec les tuiles du dashboard groupe
        nb_actives = len(store.get_active_alerts(usine_id))
        for fenetre_label in aggs:
            aggs[fenetre_label]['nb_alertes'] = nb_actives

        store.update_aggregations(usine_id, aggs)

        # ── Statut machine ────────────────────────────────────
        _calculer_machine_state(usine_id, state)

        # ── Statut global usine ───────────────────────────────
        statut_global = _calculer_statut_global(usine_id, state)

        # Mise à jour de statut_global et nb_alertes dans CURRENT_STATE
        store.update_current_state(usine_id, {
            'statut_global'      : statut_global,
            'nb_alertes_actives' : nb_actives,
        })


# ─────────────────────────────────────────────────────────────
# UTILITAIRES PUBLICS (utilisés par le dashboard)
# ─────────────────────────────────────────────────────────────

def get_trs_trend(usine_id: str, n_sessions: int = 48) -> dict:
    """
    Retourne les données de tendance TRS pour le graphique
    temps réel du dashboard.

    Retourne un dict avec :
      - timestamps : liste de timestamps simulés
      - trs_values : liste de valeurs TRS
      - ma_values  : moyenne mobile sur 10 sessions
    """
    df = store.get_buffer_as_df(usine_id)
    if df.empty:
        return {'timestamps': [], 'trs_values': [], 'ma_values': []}

    fenetre = df.tail(n_sessions).copy()

    timestamps = fenetre['timestamp'].tolist() \
        if 'timestamp' in fenetre else []
    trs_values = fenetre['TRS'].tolist() \
        if 'TRS' in fenetre else []

    # Moyenne mobile sur 10 sessions
    if len(trs_values) >= 2:
        trs_series = pd.Series(trs_values)
        ma_values  = trs_series.rolling(
            window=min(10, len(trs_series)),
            min_periods=1
        ).mean().round(4).tolist()
    else:
        ma_values = trs_values.copy()

    return {
        'timestamps' : timestamps,
        'trs_values' : trs_values,
        'ma_values'  : ma_values,
    }


def get_rebut_trend(usine_id: str, n_sessions: int = 48) -> dict:
    """
    Retourne les données de tendance taux de rebut
    pour le graphique qualité du dashboard.
    """
    df = store.get_buffer_as_df(usine_id)
    if df.empty:
        return {'timestamps': [], 'rebut_values': [], 'usure_values': []}

    fenetre = df.tail(n_sessions).copy()

    return {
        'timestamps'   : fenetre['timestamp'].tolist()
                         if 'timestamp' in fenetre else [],
        'rebut_values' : fenetre['taux_rebut'].tolist()
                         if 'taux_rebut' in fenetre else [],
        'usure_values' : fenetre['usure_cumulee_pct'].tolist()
                         if 'usure_cumulee_pct' in fenetre else [],
    }


def get_thermal_trend(usine_id: str, n_sessions: int = 48) -> dict:
    """
    Retourne le signal delta thermique pour Usine B.
    Utilisé par le graphique thermique du dashboard Usine B.
    """
    df = store.get_buffer_as_df(usine_id)
    if df.empty:
        return {'timestamps': [], 'delta_values': [], 'hdf_flags': []}

    fenetre = df.tail(n_sessions).copy()

    return {
        'timestamps'  : fenetre['timestamp'].tolist()
                        if 'timestamp' in fenetre else [],
        'delta_values': fenetre['temp_process_delta'].tolist()
                        if 'temp_process_delta' in fenetre else [],
        'hdf_flags'   : fenetre['panne_thermique'].tolist()
                        if 'panne_thermique' in fenetre else [],
    }


def get_usine_summary() -> list[dict]:
    """
    Retourne un résumé de toutes les usines pour le dashboard groupe.
    Chaque dict contient les métriques clés et le statut global.
    Tri par statut (CRITICAL en premier).
    """
    summaries = []
    ordre_statut = {'CRITICAL': 0, 'WARNING': 1, 'OK': 2, 'INIT': 3}

    for usine_id in USINES:
        state  = store.get_current_state(usine_id)
        agg_1h = store.get_aggregations(usine_id).get('1h', {})

        summaries.append({
            'usine_id'        : usine_id,
            'statut_global'   : state.get('statut_global', 'INIT'),
            'TRS_courant'     : state.get('TRS', 0.0),
            'TRS_moyen_1h'    : agg_1h.get('TRS_moyen', 0.0),
            'taux_rebut'      : state.get('taux_rebut', 0.0),
            'nb_pannes_1h'    : agg_1h.get('nb_pannes', 0),
            'nb_alertes'      : state.get('nb_alertes_actives', 0),
            'energie_1h'      : agg_1h.get('energie_totale', 0.0),
            'pieces_prod_1h'  : agg_1h.get('pieces_produites', 0),
            'timestamp_simule': state.get('timestamp'),
        })

    summaries.sort(key=lambda x: ordre_statut.get(
        x['statut_global'], 99
    ))
    return summaries


# ─────────────────────────────────────────────────────────────
# VALIDATION AU CHARGEMENT
# ─────────────────────────────────────────────────────────────
print("✓ kpi_engine.py chargé")
print(f"  Fenêtres de calcul : { {k: f'{v} sessions' for k, v in FENETRES.items()} }")