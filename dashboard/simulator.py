from __future__ import annotations
# ============================================================
# simulator.py — Moteur de simulation temps réel MECHA
#
# DÉCISION ARCHITECTURALE :
# Les données Gold sont statiques par nature.
# Le simulateur les transforme en flux vivant en les rejouant
# session par session à un rythme contrôlé.
# 1 tick = 1 seconde réelle = 30 minutes simulées.
#
# THREADING :
# Un thread daemon unique gère tous les ticks.
# Il s'arrête automatiquement avec le processus principal.
# Aucune gestion manuelle du cycle de vie du thread requise.
#
# CYCLE :
# Quand les 8 640 sessions sont épuisées, on repart du début.
# La simulation est infinie et cyclique par conception.
# ============================================================

import time
import threading
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

import store
from config import (
    USINES, GOLD_PATHS, SIMULATION_INTERVAL_S, SESSION_DURATION_MIN
)

# ─────────────────────────────────────────────────────────────
# CHARGEMENT DES DONNÉES GOLD
# Chargement unique au démarrage du module.
# Ces DataFrames restent en RAM pendant toute la simulation.
# Ne jamais recharger en cours de simulation.
# ─────────────────────────────────────────────────────────────
_gold_data: dict[str, pd.DataFrame] = {}

def _load_gold_data() -> None:
    """
    Charge les trois fichiers Parquet Gold en mémoire.
    Réinitialise l'index pour garantir un accès par position.
    Appelé une seule fois au démarrage de la simulation.
    """
    for usine_id in USINES:
        path = GOLD_PATHS[usine_id]
        if not path.exists():
            raise FileNotFoundError(
                f"Fichier Gold introuvable : {path}\n"
                f"Vérifier que le pipeline Gold a bien été exécuté."
            )
        df = pd.read_parquet(path)
        df = df.reset_index(drop=True)
        _gold_data[usine_id] = df
        print(
            f"  ✓ {usine_id} chargé "
            f"— {len(df):,} sessions · {len(df.columns)} colonnes"
        )


# ─────────────────────────────────────────────────────────────
# COLONNES À EXCLURE DU STORE
# Le timestamp du dataset Gold est historique (2024).
# On ne pousse pas le timestamp original dans le store courant
# car on génère un timestamp simulé depuis le démarrage réel.
# On conserve quand même la valeur pour référence dans le buffer.
# ─────────────────────────────────────────────────────────────
_COLS_SKIP = set()   # vide : on pousse toutes les colonnes


def _row_to_dict(row: pd.Series) -> dict:
    """
    Convertit une ligne du DataFrame Gold en dictionnaire Python natif.
    Les types numpy (int64, float64) sont convertis en types Python
    pour éviter les problèmes de sérialisation JSON et Dash.
    """
    result = {}
    for col, val in row.items():
        if col in _COLS_SKIP:
            continue
        # Conversion types numpy → Python natif
        if hasattr(val, 'item'):
            result[col] = val.item()
        elif pd.isna(val):
            result[col] = None
        else:
            result[col] = val
    return result


# ─────────────────────────────────────────────────────────────
# BOUCLE PRINCIPALE DE SIMULATION
# ─────────────────────────────────────────────────────────────
_simulation_running = False
_simulation_thread: threading.Thread | None = None

# Timestamp de démarrage réel — utilisé pour générer
# un timestamp simulé cohérent affiché dans le dashboard
_sim_start_real: datetime | None = None
_sim_start_simulated: datetime = datetime(2024, 1, 1, 6, 0, 0)


def _tick_loop() -> None:
    """
    Boucle infinie du thread daemon de simulation.
    À chaque tick :
      1. Pour chaque usine, avancer d'une session
      2. Pousser dans le store (current state + buffer)
      3. Appeler kpi_engine et alert_engine
      4. Dormir jusqu'au prochain tick
    """
    # Import ici pour éviter les imports circulaires au niveau module
    import kpi_engine
    import alert_engine

    # Index courant par usine (position dans le DataFrame)
    indices: dict[str, int] = {usine: 0 for usine in USINES}

    # Tick counter global pour le timestamp simulé
    tick = 0

    print("\n" + "="*55)
    print("  SIMULATION DÉMARRÉE")
    print(f"  Vitesse : 1 tick / {SIMULATION_INTERVAL_S}s réelle")
    print(f"  1 tick  = {SESSION_DURATION_MIN} min simulées")
    print("="*55)

    while _simulation_running:
        tick_start = time.time()

        # ── Timestamp simulé courant ──────────────────────────
        # Calculé depuis le tick pour tous les affichages dashboard
        ts_simule = _sim_start_simulated + timedelta(
            minutes=tick * SESSION_DURATION_MIN
        )

        # ── Traitement de chaque usine ────────────────────────
        for usine_id in USINES:
            df    = _gold_data[usine_id]
            n     = len(df)
            idx   = indices[usine_id]

            # Récupérer la session courante
            row     = df.iloc[idx]
            session = _row_to_dict(row)

            # Injecter le timestamp simulé courant
            # (remplace le timestamp historique Gold)
            session['timestamp']       = ts_simule
            session['session_index']   = idx

            # Pousser dans le store
            store.update_current_state(usine_id, session)
            store.push_to_buffer(usine_id, session)

            # Mettre à jour l'état du simulateur
            store.update_sim_state(usine_id, {
                'session_index'    : idx,
                'timestamp_simule' : ts_simule,
                'demarre'          : True,
                'termine'          : False,
            })

            # Avancer l'index (cyclique)
            indices[usine_id] = (idx + 1) % n

            # Log de progression toutes les 100 sessions
            if idx % 100 == 0 and idx > 0:
                pct = (idx / n) * 100
                print(
                    f"  {usine_id} · session {idx:>4}/{n} "
                    f"({pct:.0f}%) · "
                    f"TRS={session.get('TRS', 0):.3f} · "
                    f"Rebut={session.get('taux_rebut', 0)*100:.1f}%"
                )

        # ── Appels moteurs ─────────────────────────────────────
        # Ces appels sont synchrones dans le thread simulateur.
        # Ils lisent et écrivent dans le store thread-safe.
        try:
            kpi_engine.process_tick()
        except Exception as e:
            print(f"  ⚠ kpi_engine.process_tick() erreur : {e}")

        try:
            alert_engine.evaluate_tick()
        except Exception as e:
            print(f"  ⚠ alert_engine.evaluate_tick() erreur : {e}")

        # ── Contrôle du timing ─────────────────────────────────
        # On mesure le temps pris par le traitement et on déduit
        # le temps restant pour atteindre l'intervalle cible.
        # Cela garantit un tick régulier même si le traitement varie.
        elapsed   = time.time() - tick_start
        remaining = SIMULATION_INTERVAL_S - elapsed
        if remaining > 0:
            time.sleep(remaining)

        tick += 1


# ─────────────────────────────────────────────────────────────
# API PUBLIQUE DU SIMULATEUR
# ─────────────────────────────────────────────────────────────

def start() -> None:
    """
    Démarre la simulation dans un thread daemon.
    Charge les données Gold si ce n'est pas encore fait.
    Idempotent : ne fait rien si déjà démarré.
    """
    global _simulation_running, _simulation_thread, _sim_start_real

    if _simulation_running:
        print("⚠ Simulateur déjà en cours.")
        return

    print("\n" + "="*55)
    print("  CHARGEMENT DES DONNÉES GOLD")
    print("="*55)
    _load_gold_data()

    _sim_start_real      = datetime.now()
    _simulation_running  = True

    _simulation_thread   = threading.Thread(
        target=_tick_loop,
        name='mecha-simulator',
        daemon=True         # s'arrête avec le processus principal
    )
    _simulation_thread.start()
    print(f"\n  Thread simulateur démarré : {_simulation_thread.name}")
    print(f"  Démarrage réel  : {_sim_start_real.strftime('%H:%M:%S')}")
    print(f"  Démarrage simulé: {_sim_start_simulated.strftime('%Y-%m-%d %H:%M')}")


def stop() -> None:
    """
    Arrête proprement la simulation.
    Le thread daemon s'arrêtera au prochain tick.
    """
    global _simulation_running
    _simulation_running = False
    print("  Simulateur arrêté.")


def is_running() -> bool:
    """Retourne True si la simulation est active."""
    return _simulation_running


def get_progress() -> dict:
    """
    Retourne l'état d'avancement de la simulation par usine.
    Utilisé par le dashboard pour afficher la progression.
    """
    result = {}
    for usine_id in USINES:
        if usine_id in _gold_data:
            n   = len(_gold_data[usine_id])
            idx = store.get_sim_state(usine_id)['session_index']
            result[usine_id] = {
                'session_courante' : idx,
                'sessions_totales' : n,
                'progression_pct'  : round((idx / n) * 100, 1),
                'timestamp_simule' : store.get_sim_state(
                    usine_id
                )['timestamp_simule'],
            }
        else:
            result[usine_id] = {
                'session_courante' : 0,
                'sessions_totales' : 0,
                'progression_pct'  : 0.0,
                'timestamp_simule' : None,
            }
    return result


# ─────────────────────────────────────────────────────────────
# VALIDATION AU CHARGEMENT
# ─────────────────────────────────────────────────────────────
print("✓ simulator.py chargé — prêt à démarrer")