from __future__ import annotations
# ============================================================
# store.py — Mémoire centrale du système de monitoring MECHA
#
# DÉCISION ARCHITECTURALE :
# Toutes les données temps réel vivent ici.
# Aucun module ne communique directement avec un autre.
# Tout passe par le store : on écrit, on lit, on avance.
#
# THREADING :
# Le simulateur écrit dans un thread daemon.
# Le dashboard lit depuis le thread principal Dash.
# Chaque structure est protégée par un verrou indépendant
# pour éviter les corruptions de données concurrentes.
# ============================================================

import threading
import pandas as pd
from collections import deque
from datetime import datetime

from config import (
    USINES, MACHINES, BUFFER_SIZE_SESSIONS,
    ALERT_RULES
)

# ─────────────────────────────────────────────────────────────
# VERROUS THREADING
# Un verrou par structure pour granularité maximale.
# Ne jamais acquérir deux verrous simultanément (risque deadlock).
# ─────────────────────────────────────────────────────────────
_lock_current    = threading.Lock()
_lock_buffer     = threading.Lock()
_lock_alerts     = threading.Lock()
_lock_agg        = threading.Lock()
_lock_machines   = threading.Lock()

# ─────────────────────────────────────────────────────────────
# 1. CURRENT_STATE
# Une entrée par usine. Contient la dernière session reçue.
# Mise à jour à chaque tick par simulator.py
# ─────────────────────────────────────────────────────────────
CURRENT_STATE: dict[str, dict] = {
    usine: {
        # ── Horodatage ──────────────────────────────────────
        'timestamp'            : None,
        'session_index'        : 0,

        # ── Identité de la session ───────────────────────────
        'usine_id'             : usine,
        'machine_id'           : None,
        'type_piece'           : None,
        'equipe'               : None,

        # ── Capteurs ─────────────────────────────────────────
        'temp_air_c'           : 0.0,
        'temp_process_c'       : 0.0,
        'temp_process_delta'   : 0.0,
        'vitesse_rotation_rpm' : 0.0,
        'couple_nm'            : 0.0,

        # ── Usure outil ──────────────────────────────────────
        'usure_outil_min'      : 0.0,
        'usure_cumulee_pct'    : 0.0,
        'remplacement_outil'   : 0,

        # ── Pannes ───────────────────────────────────────────
        'panne_machine'        : 0,
        'panne_usure_outil'    : 0,
        'panne_thermique'      : 0,
        'panne_puissance'      : 0,
        'panne_surcharge'      : 0,
        'panne_aleatoire'      : 0,
        'type_panne'           : 'Aucune',
        'duree_arret_min'      : 0.0,
        'nb_pannes_7j'         : 0,

        # ── Production ───────────────────────────────────────
        'temps_cycle_min'      : 0.0,
        'derive_cycle_pct'     : 0.0,
        'pieces_produites'     : 0,
        'taux_rebut'           : 0.0,
        'pieces_rebutees'      : 0,
        'consommation_kwh'     : 0.0,
        'rupture_appro'        : 0,
        'indice_stabilite_process': 0.0,
        'intervention_maintenance': 0,

        # ── KPIs TRS ─────────────────────────────────────────
        'disponibilite'        : 0.0,
        'performance'          : 0.0,
        'qualite'              : 0.0,
        'TRS'                  : 0.0,

        # ── Statut global (calculé par kpi_engine) ───────────
        'statut_global'        : 'INIT',   # INIT / OK / WARNING / CRITICAL
        'nb_alertes_actives'   : 0,
    }
    for usine in USINES
}

# ─────────────────────────────────────────────────────────────
# 2. BUFFER_24H
# Historique glissant des N dernières sessions par usine.
# deque avec maxlen : quand plein, la plus ancienne session
# est automatiquement supprimée (FIFO circulaire).
# Lu par kpi_engine pour les agrégations et par dashboard
# pour alimenter les graphiques temporels.
# ─────────────────────────────────────────────────────────────
BUFFER_24H: dict[str, deque] = {
    usine: deque(maxlen=BUFFER_SIZE_SESSIONS)
    for usine in USINES
}

# ─────────────────────────────────────────────────────────────
# 3. ALERT_TABLE
# DataFrame de toutes les alertes déclenchées depuis le démarrage.
# Écrit par alert_engine, lu par dashboard.
# Conserve l'historique complet de la session de simulation.
# ─────────────────────────────────────────────────────────────
ALERT_TABLE: pd.DataFrame = pd.DataFrame(columns=[
    'alert_id',           # identifiant unique str : usine_regle_timestamp
    'timestamp_debut',    # datetime de déclenchement
    'timestamp_fin',      # datetime de résolution (None si encore active)
    'usine_id',           # Usine_A / Usine_B / Usine_C
    'machine_id',         # M01 à M04
    'rule_name',          # clé dans ALERT_RULES de config.py
    'label',              # label lisible pour l'affichage
    'kpi',                # colonne KPI concernée
    'valeur_observee',    # valeur au moment du déclenchement
    'seuil_franchi',      # valeur du seuil dépassé
    'type_seuil',         # UCL / LCL / FIXED
    'severite',           # INFO / WARNING / CRITICAL
    'statut',             # ACTIVE / RESOLVED / ACKNOWLEDGED
    'message_court',      # une ligne pour le panel alertes
    'message_detail',     # texte complet avec recommandation
    'acquittee',          # bool — opérateur a vu l'alerte
    'duree_active_min',   # calculée à la résolution
])

# ─────────────────────────────────────────────────────────────
# 4. AGGREGATIONS
# KPIs agrégés par fenêtre temporelle.
# Calculés par kpi_engine depuis BUFFER_24H.
# Le dashboard lit directement ici sans recalculer.
# ─────────────────────────────────────────────────────────────
_agg_vide = {
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

AGGREGATIONS: dict[str, dict[str, dict]] = {
    usine: {
        '1h' : _agg_vide.copy(),
        '8h' : _agg_vide.copy(),
        '24h': _agg_vide.copy(),
    }
    for usine in USINES
}

# ─────────────────────────────────────────────────────────────
# 5. MACHINE_STATE
# Statut et métriques clés par machine par usine.
# Calculé par kpi_engine depuis CURRENT_STATE.
# Affiché dans la grille machines du dashboard.
# ─────────────────────────────────────────────────────────────
MACHINE_STATE: dict[str, dict[str, dict]] = {
    usine: {
        machine: {
            'statut'          : 'INIT',   # INIT/EN_PRODUCTION/ARRET/MAINTENANCE
            'usure_pct'       : 0.0,
            'taux_rebut'      : 0.0,
            'temps_cycle_min' : 0.0,
            'derniere_panne'  : None,
            'temps_en_etat_s' : 0,        # secondes dans l'état courant
        }
        for machine in MACHINES
    }
    for usine in USINES
}

# ─────────────────────────────────────────────────────────────
# ÉTAT DU SIMULATEUR
# Suivi de l'avancement de la simulation par usine.
# Écrit par simulator, lu par dashboard pour afficher
# l'horodatage simulé courant.
# ─────────────────────────────────────────────────────────────
SIM_STATE: dict[str, dict] = {
    usine: {
        'session_index'    : 0,
        'timestamp_simule' : None,
        'demarre'          : False,
        'termine'          : False,
    }
    for usine in USINES
}

# ─────────────────────────────────────────────────────────────
# ÉTAT DES COOLDOWNS ALERTES
# Suivi interne pour l'anti-bruit de l'alert_engine.
# Mémorise la dernière fois que chaque règle a été déclenchée
# par usine, pour respecter le cooldown défini dans config.py.
# ─────────────────────────────────────────────────────────────
ALERT_COOLDOWNS: dict[str, dict[str, datetime | None]] = {
    usine: {rule: None for rule in ALERT_RULES}
    for usine in USINES
}

# Compteurs de persistance : nombre de sessions consécutives
# en dépassement par règle et par usine.
ALERT_PERSISTENCE: dict[str, dict[str, int]] = {
    usine: {rule: 0 for rule in ALERT_RULES}
    for usine in USINES
}

# ─────────────────────────────────────────────────────────────
# INJECTION DE PANNES (mode démonstration)
# Overrides appliqués par-dessus les données du simulateur.
# Le simulateur continue de tourner — seuls les champs listés
# ici remplacent les valeurs jusqu'à un appel clear_fault().
# ─────────────────────────────────────────────────────────────
_FAULT_INJECTIONS: dict[str, dict] = {usine: {} for usine in USINES}

# ─────────────────────────────────────────────────────────────
# FONCTIONS D'ACCÈS THREAD-SAFE
# Chaque fonction acquiert le bon verrou, opère, libère.
# Le reste du système utilise ces fonctions, jamais les
# structures directement depuis un autre thread.
# ─────────────────────────────────────────────────────────────

def update_current_state(usine_id: str, session: dict) -> None:
    """
    Met à jour l'état courant d'une usine avec les données
    de la nouvelle session. Appelé par simulator à chaque tick.
    """
    with _lock_current:
        CURRENT_STATE[usine_id].update(session)


def get_current_state(usine_id: str) -> dict:
    """
    Retourne une copie de l'état courant d'une usine.
    Applique les overrides de fault injection par-dessus les données simulateur.
    """
    with _lock_current:
        state = CURRENT_STATE[usine_id].copy()
        state.update(_FAULT_INJECTIONS[usine_id])
        return state


def inject_fault(usine_id: str, overrides: dict) -> None:
    """Injecte des valeurs de panne par-dessus le simulateur."""
    with _lock_current:
        _FAULT_INJECTIONS[usine_id].update(overrides)


def clear_fault(usine_id: str) -> None:
    """Supprime toutes les injections — le simulateur reprend normalement."""
    with _lock_current:
        _FAULT_INJECTIONS[usine_id].clear()


def get_fault_injection(usine_id: str) -> dict:
    """Retourne les overrides actifs (vide = aucune injection)."""
    with _lock_current:
        return _FAULT_INJECTIONS[usine_id].copy()


def get_all_current_states() -> dict:
    """
    Retourne une copie de l'état courant de toutes les usines.
    Utilisé par le dashboard groupe.
    """
    with _lock_current:
        return {u: CURRENT_STATE[u].copy() for u in USINES}


def push_to_buffer(usine_id: str, session: dict) -> None:
    """
    Ajoute une session au buffer glissant 24h d'une usine.
    Quand le buffer est plein, la session la plus ancienne
    est automatiquement supprimée par la deque.
    """
    with _lock_buffer:
        BUFFER_24H[usine_id].append(session.copy())


def get_buffer(usine_id: str) -> list:
    """
    Retourne le contenu du buffer 24h d'une usine sous forme
    de liste de dicts. Copie défensive.
    """
    with _lock_buffer:
        return list(BUFFER_24H[usine_id])


def get_buffer_as_df(usine_id: str) -> pd.DataFrame:
    """
    Retourne le buffer 24h d'une usine sous forme de DataFrame.
    Pratique pour les calculs d'agrégation dans kpi_engine.
    Retourne un DataFrame vide si le buffer est vide.
    """
    with _lock_buffer:
        data = list(BUFFER_24H[usine_id])
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def append_alert(alert: dict) -> None:
    """
    Ajoute une nouvelle alerte à ALERT_TABLE.
    Appelé par alert_engine lors du déclenchement d'une alerte.
    """
    global ALERT_TABLE
    with _lock_alerts:
        new_row = pd.DataFrame([alert])
        ALERT_TABLE = pd.concat(
            [ALERT_TABLE, new_row], ignore_index=True
        )


def resolve_alert(alert_id: str) -> None:
    """
    Marque une alerte comme résolue avec l'heure de résolution
    et calcule sa durée active.
    Appelé par alert_engine quand la condition n'est plus vraie.
    """
    with _lock_alerts:
        mask = ALERT_TABLE['alert_id'] == alert_id
        if mask.any():
            now = datetime.utcnow()
            debut = ALERT_TABLE.loc[mask, 'timestamp_debut'].iloc[0]
            duree = (now - debut).total_seconds() / 60
            ALERT_TABLE.loc[mask, 'statut']          = 'RESOLVED'
            ALERT_TABLE.loc[mask, 'timestamp_fin']   = now
            ALERT_TABLE.loc[mask, 'duree_active_min'] = round(duree, 1)


def get_active_alerts(usine_id: str | None = None) -> pd.DataFrame:
    """
    Retourne les alertes actives.
    Si usine_id est fourni, filtre sur cette usine uniquement.
    Retourne une copie triée par sévérité (CRITICAL en premier).
    """
    with _lock_alerts:
        df = ALERT_TABLE[ALERT_TABLE['statut'] == 'ACTIVE'].copy()
    if usine_id:
        df = df[df['usine_id'] == usine_id]
    ordre = {'CRITICAL': 0, 'WARNING': 1, 'INFO': 2}
    df['_ordre'] = df['severite'].map(ordre)
    return df.sort_values('_ordre').drop(columns=['_ordre'])


def get_alert_history(
    usine_id: str | None = None,
    n_last: int = 50
) -> pd.DataFrame:
    """
    Retourne l'historique des N dernières alertes (actives + résolues).
    Utilisé par l'onglet Alertes du dashboard usine.
    """
    with _lock_alerts:
        df = ALERT_TABLE.copy()
    if usine_id:
        df = df[df['usine_id'] == usine_id]
    return df.tail(n_last).sort_values(
        'timestamp_debut', ascending=False
    )


def update_aggregations(usine_id: str, aggs: dict) -> None:
    """
    Met à jour les agrégations fenêtrées d'une usine.
    Appelé par kpi_engine après chaque recalcul.
    aggs doit contenir les clés '1h', '8h', '24h'.
    """
    with _lock_agg:
        AGGREGATIONS[usine_id].update(aggs)


def get_aggregations(usine_id: str) -> dict:
    """
    Retourne une copie des agrégations d'une usine.
    """
    with _lock_agg:
        return {
            k: v.copy()
            for k, v in AGGREGATIONS[usine_id].items()
        }


def update_machine_state(
    usine_id: str,
    machine_id: str,
    state: dict
) -> None:
    """
    Met à jour le statut d'une machine spécifique.
    Appelé par kpi_engine depuis la session courante.
    """
    with _lock_machines:
        MACHINE_STATE[usine_id][machine_id].update(state)


def get_machine_states(usine_id: str) -> dict:
    """
    Retourne une copie des états de toutes les machines d'une usine.
    """
    with _lock_machines:
        return {
            m: s.copy()
            for m, s in MACHINE_STATE[usine_id].items()
        }


def update_sim_state(usine_id: str, state: dict) -> None:
    """Met à jour l'état du simulateur pour une usine."""
    SIM_STATE[usine_id].update(state)


def get_sim_state(usine_id: str) -> dict:
    """Retourne l'état courant du simulateur pour une usine."""
    return SIM_STATE[usine_id].copy()


def reset_store() -> None:
    """
    Réinitialise toutes les structures à leur état vide initial.
    Utile pour redémarrer la simulation sans relancer le processus.
    Appelé manuellement ou via un bouton reset dans le dashboard.
    """
    global ALERT_TABLE
    with _lock_buffer:
        for usine in USINES:
            BUFFER_24H[usine].clear()
    with _lock_alerts:
        ALERT_TABLE = ALERT_TABLE.iloc[0:0].copy()
    with _lock_agg:
        for usine in USINES:
            for fenetre in ['1h', '8h', '24h']:
                AGGREGATIONS[usine][fenetre] = _agg_vide.copy()
    with _lock_machines:
        for usine in USINES:
            for machine in MACHINES:
                MACHINE_STATE[usine][machine] = {
                    'statut'          : 'INIT',
                    'usure_pct'       : 0.0,
                    'taux_rebut'      : 0.0,
                    'temps_cycle_min' : 0.0,
                    'derniere_panne'  : None,
                    'temps_en_etat_s' : 0,
                }
    for usine in USINES:
        for rule in ALERT_RULES:
            ALERT_COOLDOWNS[usine][rule]    = None
            ALERT_PERSISTENCE[usine][rule]  = 0
        SIM_STATE[usine].update({
            'session_index'    : 0,
            'timestamp_simule' : None,
            'demarre'          : False,
            'termine'          : False,
        })


# ─────────────────────────────────────────────────────────────
# VALIDATION AU CHARGEMENT
# ─────────────────────────────────────────────────────────────
print("✓ store.py chargé")
print(f"  Usines initialisées   : {USINES}")
print(f"  Buffer size           : {BUFFER_SIZE_SESSIONS} sessions (24h)")
print(f"  Colonnes alert table  : {len(ALERT_TABLE.columns)}")
print(f"  Règles d'alerte       : {list(ALERT_RULES.keys())}")