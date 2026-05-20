from __future__ import annotations
# ============================================================
# alert_engine.py — Moteur d'alertes industrielles MECHA
#
# DÉCISION ARCHITECTURALE :
# Moteur générique piloté par les règles de config.py.
# Ajouter une règle = modifier config.py uniquement.
# Les messages sont construits par des fonctions dédiées
# par famille de problème industriel.
#
# APPELÉ PAR : simulator.py à chaque tick
# LIT DEPUIS : store.CURRENT_STATE, store.ALERT_TABLE,
#              store.ALERT_COOLDOWNS, store.ALERT_PERSISTENCE
# ÉCRIT DANS : store.ALERT_TABLE via store.append_alert()
#              et store.resolve_alert()
# ============================================================

import json
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import store
from config import (
    USINES, ALERT_RULES, LIMITS_PATHS,
    USINE_DOMINANT_PROBLEM,
)

# ─────────────────────────────────────────────────────────────
# CHARGEMENT DES LIMITES SPC
# Chargé une seule fois au démarrage du module.
# Structure aplatie pour accès rapide :
# _spc_limits['Usine_A']['taux_rebut.ucl'] = 0.09
# ─────────────────────────────────────────────────────────────
_spc_limits: dict[str, dict[str, float]] = {}

def _load_spc_limits() -> None:
    """
    Charge les fichiers JSON de limites SPC Gold pour chaque usine.
    Aplatit la structure imbriquée en clés composites kpi.metric.
    Ex : limites['TRS']['ucl'] → _spc_limits['Usine_A']['TRS.ucl']
    """
    for usine_id in USINES:
        path = LIMITS_PATHS[usine_id]
        if not path.exists():
            print(f"  ⚠ Limites SPC introuvables : {path}")
            _spc_limits[usine_id] = {}
            continue

        with open(path, 'r') as f:
            raw = json.load(f)

        flat = {}
        for kpi_name, metrics in raw.items():
            if isinstance(metrics, dict):
                for metric_name, value in metrics.items():
                    if isinstance(value, (int, float)):
                        flat[f"{kpi_name}.{metric_name}"] = float(value)

        _spc_limits[usine_id] = flat
        print(
            f"  ✓ Limites SPC chargées : {usine_id} "
            f"— {len(flat)} paramètres"
        )


def _get_seuil(usine_id: str, rule: dict) -> float | None:
    """
    Résout le seuil d'une règle selon sa source.
    Retourne None si le seuil n'est pas disponible.
    """
    if rule['seuil_src'] == 'fixed':
        return float(rule['seuil_value'])

    if rule['seuil_src'] == 'json':
        key = rule.get('seuil_key', '')
        return _spc_limits.get(usine_id, {}).get(key)

    return None


# ─────────────────────────────────────────────────────────────
# ÉVALUATION DES CONDITIONS
# ─────────────────────────────────────────────────────────────

def _check_condition(
    state: dict,
    rule: dict,
    seuil: float
) -> tuple[bool, float]:
    """
    Évalue si la condition d'une règle est vraie pour l'état courant.
    Retourne (condition_vraie, valeur_observee).
    """
    kpi     = rule['kpi']
    valeur  = state.get(kpi)

    if valeur is None:
        return False, 0.0

    valeur = float(valeur)
    cond   = rule['condition']

    if cond == 'above':
        return valeur > seuil, valeur
    if cond == 'below':
        return valeur < seuil, valeur
    if cond == 'equals':
        return valeur == seuil, valeur

    return False, valeur


def _check_composite_combinaison_critique(state: dict) -> tuple[bool, float]:
    """
    Règle composite Usine C : REF03 + Nuit + rebut > UCL.
    Retourne (condition_vraie, taux_rebut_observé).
    La combinaison la plus défavorable du portefeuille.
    """
    est_ref03 = state.get('type_piece') == 'REF03'
    est_nuit  = state.get('equipe') == 'Nuit'
    rebut     = float(state.get('taux_rebut', 0.0))
    ucl_rebut = _spc_limits.get('Usine_C', {}).get('taux_rebut.ucl', 0.33)

    condition = est_ref03 and est_nuit and (rebut > ucl_rebut)
    return condition, rebut


# ─────────────────────────────────────────────────────────────
# MOTEUR GÉNÉRIQUE D'ÉVALUATION
# ─────────────────────────────────────────────────────────────

# Compteur de sessions normales consécutives pour chaque alerte active
# avant résolution : {alert_id: int}
_resolution_buffers: dict[str, int] = {}

# Mapping rule_name → seuil de sessions normales avant résolution
_RESOLUTION_SEUILS = {
    'machine_arretee'        : 1,
    'rupture_appro'          : 1,
    'usure_critique'         : 2,
    'usure_warning'          : 1,
    'derive_qualite'         : 2,
    'derive_cycle'           : 3,
    'derive_thermique'       : 2,
    'cluster_thermique'      : 2,
    'isp_bas'                : 2,
    'combinaison_critique'   : 1,
    'trs_critique'           : 3,
}

# Seuil de sessions actives pour escalade WARNING → CRITICAL
_ESCALADE_SEUILS = {
    'derive_qualite' : 8,
    'cluster_thermique': 5,
}

# Tracking des sessions actives par alerte : {alert_id: int}
_sessions_actives: dict[str, int] = {}


def _get_active_alert_id(
    usine_id: str,
    rule_name: str
) -> str | None:
    """
    Retourne l'alert_id de l'alerte active pour une usine et une règle.
    None si aucune alerte active.
    """
    alertes = store.get_active_alerts(usine_id)
    if alertes.empty:
        return None
    mask = alertes['rule_name'] == rule_name
    if not mask.any():
        return None
    return alertes.loc[mask, 'alert_id'].iloc[0]


def _evaluate_rule(
    usine_id: str,
    rule_name: str,
    rule: dict,
    state: dict,
) -> None:
    """
    Évalue une règle pour une usine donnée.
    Gère le cycle de vie complet : création, escalade, résolution.

    Séquence :
      1. Résoudre le seuil
      2. Évaluer la condition
      3. Gérer la persistance (compteur sessions)
      4. Vérifier le cooldown
      5. Créer l'alerte si nécessaire
      6. Gérer l'escalade si alerte déjà active
      7. Gérer la résolution si condition redevenue fausse
    """
    # ── Cas spécial : règle composite ────────────────────────
    if rule_name == 'combinaison_critique':
        condition_vraie, valeur = _check_composite_combinaison_critique(state)
        seuil = _spc_limits.get(usine_id, {}).get('taux_rebut.ucl', 0.33)
    else:
        seuil = _get_seuil(usine_id, rule)
        if seuil is None:
            return
        condition_vraie, valeur = _check_condition(state, rule, seuil)

    # ── Alerte déjà active pour cette règle ? ─────────────────
    alert_id_actif = _get_active_alert_id(usine_id, rule_name)

    # ── Condition VRAIE ───────────────────────────────────────
    if condition_vraie:

        # Réinitialiser le buffer de résolution
        if alert_id_actif:
            _resolution_buffers[alert_id_actif] = 0

        # Incrémenter persistance
        store.ALERT_PERSISTENCE[usine_id][rule_name] += 1
        persist_count = store.ALERT_PERSISTENCE[usine_id][rule_name]

        # Alerte déjà active : gérer l'escalade
        if alert_id_actif:
            _sessions_actives[alert_id_actif] = \
                _sessions_actives.get(alert_id_actif, 0) + 1
            seuil_escalade = _ESCALADE_SEUILS.get(rule_name)
            if seuil_escalade and \
               _sessions_actives[alert_id_actif] >= seuil_escalade:
                # Escalader en CRITICAL in-place
                with store._lock_alerts:
                    mask = store.ALERT_TABLE['alert_id'] == alert_id_actif
                    if mask.any():
                        sev_actuelle = store.ALERT_TABLE.loc[
                            mask, 'severite'
                        ].iloc[0]
                        if sev_actuelle == 'WARNING':
                            store.ALERT_TABLE.loc[
                                mask, 'severite'
                            ] = 'CRITICAL'
            return

        # Vérifier persistance minimale
        if persist_count < rule.get('persistence', 1):
            return

        # Vérifier cooldown
        last_trigger = store.ALERT_COOLDOWNS[usine_id].get(rule_name)
        cooldown_s   = rule.get('cooldown_s', 0)
        if last_trigger and cooldown_s > 0:
            elapsed = (datetime.utcnow() - last_trigger).total_seconds()
            if elapsed < cooldown_s:
                return

        # ── CRÉER L'ALERTE ────────────────────────────────────
        ts_now   = datetime.utcnow()
        alert_id = (
            f"{usine_id}_{rule_name}_"
            f"{int(ts_now.timestamp())}"
        )

        contexte = _build_contexte(state, valeur, seuil, usine_id, rule_name)
        msg_court, msg_detail, recommandation = _dispatch_message(
            rule_name, rule, contexte
        )

        alert = {
            'alert_id'          : alert_id,
            'timestamp_debut'   : ts_now,
            'timestamp_fin'     : None,
            'usine_id'          : usine_id,
            'machine_id'        : state.get('machine_id', 'N/A'),
            'rule_name'         : rule_name,
            'label'             : rule.get('label', rule_name),
            'kpi'               : rule.get('kpi', ''),
            'valeur_observee'   : round(valeur, 4),
            'seuil_franchi'     : round(seuil, 4),
            'type_seuil'        : _type_seuil(rule),
            'severite'          : rule.get('severite', 'INFO'),
            'statut'            : 'ACTIVE',
            'message_court'     : msg_court,
            'message_detail'    : msg_detail,
            'recommandation'    : recommandation,
            'acquittee'         : False,
            'duree_active_min'  : None,
            'contexte_piece'    : state.get('type_piece', ''),
            'contexte_equipe'   : state.get('equipe', ''),
            'sessions_actives'  : 1,
        }

        store.append_alert(alert)
        store.ALERT_COOLDOWNS[usine_id][rule_name] = ts_now
        store.ALERT_PERSISTENCE[usine_id][rule_name] = 0
        _sessions_actives[alert_id] = 1
        _resolution_buffers[alert_id] = 0

    # ── Condition FAUSSE ──────────────────────────────────────
    else:
        # Décrémenter persistance
        store.ALERT_PERSISTENCE[usine_id][rule_name] = max(
            0, store.ALERT_PERSISTENCE[usine_id][rule_name] - 1
        )

        if alert_id_actif:
            # Incrémenter buffer de résolution
            _resolution_buffers[alert_id_actif] = \
                _resolution_buffers.get(alert_id_actif, 0) + 1

            seuil_resol = _RESOLUTION_SEUILS.get(rule_name, 1)

            if _resolution_buffers[alert_id_actif] >= seuil_resol:
                # Construire message de résolution
                state_resol  = store.get_current_state(usine_id)
                contexte_res = _build_contexte(
                    state_resol, valeur, seuil, usine_id, rule_name
                )
                # Durée de l'incident pour le message
                with store._lock_alerts:
                    mask = store.ALERT_TABLE['alert_id'] == alert_id_actif
                    if mask.any():
                        debut = store.ALERT_TABLE.loc[
                            mask, 'timestamp_debut'
                        ].iloc[0]
                        duree_min = round(
                            (datetime.utcnow() - debut).total_seconds() / 60,
                            1
                        )
                        contexte_res['duree_incident_min'] = duree_min

                msg_court_r, msg_detail_r, _ = build_message_resolved(
                    rule, contexte_res
                )

                # Mettre à jour le message avant de résoudre
                with store._lock_alerts:
                    mask = store.ALERT_TABLE['alert_id'] == alert_id_actif
                    if mask.any():
                        store.ALERT_TABLE.loc[
                            mask, 'message_court'
                        ] = msg_court_r

                store.resolve_alert(alert_id_actif)

                # Nettoyage des trackers
                _resolution_buffers.pop(alert_id_actif, None)
                _sessions_actives.pop(alert_id_actif, None)


def _type_seuil(rule: dict) -> str:
    """Détermine le label du type de seuil pour ALERT_TABLE."""
    if rule['seuil_src'] == 'fixed':
        return 'FIXED'
    key = rule.get('seuil_key', '')
    if 'ucl' in key: return 'UCL'
    if 'lcl' in key: return 'LCL'
    if 'uwl' in key: return 'UWL'
    if 'lwl' in key: return 'LWL'
    return 'SPC'


# ─────────────────────────────────────────────────────────────
# CONSTRUCTION DU CONTEXTE POUR LES MESSAGES
# ─────────────────────────────────────────────────────────────

def _build_contexte(
    state: dict,
    valeur: float,
    seuil: float,
    usine_id: str,
    rule_name: str,
) -> dict:
    """
    Construit le dictionnaire de contexte passé aux fonctions
    de construction de messages. Centralise toute la logique
    d'extraction des valeurs utiles depuis l'état courant.
    """
    ts = state.get('timestamp')
    ts_str = ts.strftime('%H:%M') if hasattr(ts, 'strftime') else 'N/A'

    return {
        'usine_id'         : usine_id,
        'usine_label'      : f"Usine {usine_id.split('_')[1]}",
        'machine_id'       : state.get('machine_id', 'N/A'),
        'type_piece'       : state.get('type_piece', 'N/A'),
        'equipe'           : state.get('equipe', 'N/A'),
        'timestamp_str'    : ts_str,
        'valeur'           : valeur,
        'seuil'            : seuil,
        'ecart_pct'        : round(((valeur - seuil) / seuil * 100), 1)
                             if seuil != 0 else 0.0,
        'TRS'              : state.get('TRS', 0.0),
        'taux_rebut'       : state.get('taux_rebut', 0.0),
        'usure_pct'        : state.get('usure_cumulee_pct', 0.0),
        'delta_T'          : state.get('temp_process_delta', 0.0),
        'type_panne'       : state.get('type_panne', 'N/A'),
        'duree_arret'      : state.get('duree_arret_min', 0.0),
        'nb_pannes_7j'     : state.get('nb_pannes_7j', 0),
        'derive_cycle_pct' : state.get('derive_cycle_pct', 0.0),
        'isp'              : state.get('indice_stabilite_process', 0.0),
        'pieces_prod'      : state.get('pieces_produites', 0),
        'dominant_problem' : USINE_DOMINANT_PROBLEM.get(usine_id, ''),
        'duree_incident_min': 0.0,
    }


# ─────────────────────────────────────────────────────────────
# DISPATCHER DES MESSAGES
# ─────────────────────────────────────────────────────────────

def _dispatch_message(
    rule_name: str,
    rule: dict,
    ctx: dict,
) -> tuple[str, str, str]:
    """
    Route vers la bonne fonction de construction de message
    selon la famille du problème industriel.
    Retourne (message_court, message_detail, recommandation).
    """
    if rule_name in ('machine_arretee',):
        return build_message_arret(rule, ctx)

    if rule_name in ('derive_qualite', 'combinaison_critique'):
        return build_message_qualite(rule, ctx)

    if rule_name in ('derive_thermique', 'cluster_thermique'):
        return build_message_thermique(rule, ctx)

    if rule_name in ('usure_warning', 'usure_critique'):
        return build_message_usure(rule, ctx)

    if rule_name in ('rupture_appro',):
        return build_message_appro(rule, ctx)

    if rule_name in ('isp_bas', 'trs_critique', 'derive_cycle'):
        return build_message_process(rule, ctx)

    # Fallback générique
    return (
        f"{rule.get('label', rule_name)} — {ctx['usine_label']} · "
        f"{ctx['machine_id']}",
        f"KPI : {rule.get('kpi', 'N/A')} · "
        f"Valeur : {ctx['valeur']:.3f} · Seuil : {ctx['seuil']:.3f}",
        rule.get('message', 'Consulter le responsable technique.')
    )


# ─────────────────────────────────────────────────────────────
# FONCTIONS DE CONSTRUCTION DE MESSAGES
# ─────────────────────────────────────────────────────────────

def build_message_arret(rule: dict, ctx: dict) -> tuple[str, str, str]:
    duree_str = (
        f"{int(ctx['duree_arret'])//60:02d}h"
        f"{int(ctx['duree_arret'])%60:02d}"
        if ctx['duree_arret'] > 0 else "en cours"
    )
    pertes_est = max(0, int(ctx['duree_arret'] / 0.5))

    court = (
        f"ARRÊT MACHINE — {ctx['usine_label']} · "
        f"{ctx['machine_id']} · {ctx['type_panne']}"
    )

    detail = (
        f"PROBLÈME : La machine {ctx['machine_id']} est à l'arrêt.\n"
        f"Mode de panne détecté : {ctx['type_panne']}.\n"
        f"Durée d'arrêt : {duree_str}.\n\n"
        f"CONTEXTE : Pièce en cours : {ctx['type_piece']}. "
        f"Équipe en poste : {ctx['equipe']}.\n"
        f"Usure outil au moment de l'arrêt : "
        f"{ctx['usure_pct']:.1f}%.\n\n"
        f"IMPACT : Production interrompue sur {ctx['machine_id']}.\n"
        f"Perte estimée : {pertes_est} pièces.\n\n"
        f"ACTION : Intervention maintenance requise immédiatement.\n"
        f"Rediriger la charge vers les machines disponibles."
    )

    reco = (
        f"Intervention immédiate sur {ctx['machine_id']}. "
        f"Durée estimée : 90 à 120 min selon type panne."
    )
    return court, detail, reco


def build_message_qualite(rule: dict, ctx: dict) -> tuple[str, str, str]:
    rebut_pct = ctx['taux_rebut'] * 100
    seuil_pct = ctx['seuil'] * 100
    ecart     = rebut_pct - seuil_pct

    est_combinaison = (
        ctx['type_piece'] == 'REF03' and ctx['equipe'] == 'Nuit'
    )
    prefixe = "QUALITÉ CRITIQUE" if est_combinaison else "DÉRIVE QUALITÉ"

    court = (
        f"{prefixe} — {ctx['usine_label']} · "
        f"{ctx['type_piece']} · {ctx['equipe']} · "
        f"{rebut_pct:.1f}%"
    )

    contexte_combo = (
        "\nCOMBINAISON CRITIQUE : REF03 en production par "
        "l'équipe de nuit.\n"
        "Cette combinaison génère structurellement le rebut "
        "le plus élevé de l'usine."
    ) if est_combinaison else ""

    detail = (
        f"PROBLÈME : Taux de rebut à {rebut_pct:.1f}% "
        f"(UCL : {seuil_pct:.1f}%, écart : +{ecart:.1f} pts).\n\n"
        f"CONTEXTE : Pièce : {ctx['type_piece']}. "
        f"Équipe : {ctx['equipe']}. "
        f"Machine : {ctx['machine_id']}.{contexte_combo}\n\n"
        f"IMPACT : Production non conforme en cours.\n"
        f"TRS qualité courant : {(1-ctx['taux_rebut'])*100:.1f}%.\n\n"
        f"ACTION : Contrôler les réglages process.\n"
        f"Vérifier l'état de l'outillage et la matière première.\n"
        f"Alerter le responsable qualité si dépassement > 25%."
    )

    reco = (
        "Contrôle immédiat réglages process et matière. "
        "Seuil d'arrêt de lot : 25%."
    )
    return court, detail, reco


def build_message_thermique(rule: dict, ctx: dict) -> tuple[str, str, str]:
    est_cluster = 'cluster' in rule.get('rule_name', '')

    if est_cluster:
        court = (
            f"CLUSTER THERMIQUE — {ctx['usine_label']} · "
            f"{ctx['nb_pannes_7j']} pannes HDF / 7j"
        )
        detail = (
            f"PROBLÈME : {ctx['nb_pannes_7j']} pannes thermiques "
            f"enregistrées sur les 7 derniers jours.\n"
            f"Cluster de pannes HDF en cours sur "
            f"{ctx['usine_label']}.\n\n"
            f"CONTEXTE : Machine active : {ctx['machine_id']}. "
            f"Delta T courant : {ctx['delta_T']:.1f} K.\n\n"
            f"IMPACT : Risque d'aggravation du cluster. "
            f"Arrêts répétés prévisibles.\n\n"
            f"ACTION : Inspection système de refroidissement. "
            f"Maintenance préventive programmée sur toutes les machines."
        )
        reco = "Inspection refroidissement urgente. Maintenance préventive."

    else:
        court = (
            f"DÉRIVE THERMIQUE — {ctx['usine_label']} · "
            f"Delta T : {ctx['delta_T']:.1f} K "
            f"(seuil : {ctx['seuil']:.1f} K)"
        )
        detail = (
            f"PROBLÈME : Delta thermique à {ctx['delta_T']:.1f} K, "
            f"sous le seuil critique de {ctx['seuil']:.1f} K.\n\n"
            f"CONTEXTE : Ce signal précède les pannes HDF "
            f"de 20 à 40 min en moyenne.\n"
            f"{ctx['nb_pannes_7j']} pannes HDF sur les 7 derniers jours.\n"
            f"Machine active : {ctx['machine_id']}.\n\n"
            f"IMPACT : Risque de panne thermique élevé "
            f"dans la prochaine heure.\n"
            f"Durée arrêt typique si panne HDF : 90 à 240 min.\n\n"
            f"ACTION : Vérifier le système de refroidissement.\n"
            f"Réduire la cadence à 80% à titre préventif."
        )
        reco = (
            f"Inspection refroidissement {ctx['machine_id']}. "
            f"Réduire cadence à 80%."
        )

    return court, detail, reco


def build_message_usure(rule: dict, ctx: dict) -> tuple[str, str, str]:
    usure     = ctx['usure_pct']
    is_crit   = usure >= 90.0
    temps_est = max(0, round((100 - usure) / max(usure, 1) * 120, 0))

    niveau = "CRITIQUE" if is_crit else "ÉLEVÉE"

    court = (
        f"USURE OUTIL {niveau} — {ctx['usine_label']} · "
        f"{ctx['machine_id']} · {usure:.1f}%"
    )

    urgence = (
        "Remplacement immédiat requis avant la prochaine session."
        if is_crit else
        f"Remplacement recommandé dans environ {temps_est:.0f} min."
    )

    detail = (
        f"PROBLÈME : Usure outil à {usure:.1f}% "
        f"(seuil : {ctx['seuil']:.0f}%).\n\n"
        f"CONTEXTE : Machine {ctx['machine_id']}. "
        f"Pièce en cours : {ctx['type_piece']}.\n\n"
        f"IMPACT : {'Risque de panne TWF imminent.' if is_crit else 'Dégradation progressive du rebut attendue.'}\n\n"
        f"ACTION : {urgence}"
    )

    reco = urgence
    return court, detail, reco


def build_message_appro(rule: dict, ctx: dict) -> tuple[str, str, str]:
    court = f"RUPTURE APPRO — {ctx['usine_label']} · Production arrêtée"

    detail = (
        f"PROBLÈME : Rupture d'approvisionnement détectée sur "
        f"{ctx['usine_label']}.\n"
        f"Production à l'arrêt faute de matière.\n\n"
        f"CONTEXTE : Machine concernée : {ctx['machine_id']}. "
        f"Équipe : {ctx['equipe']}.\n\n"
        f"IMPACT : Production 0 pièce jusqu'à résolution.\n"
        f"Impact direct sur les délais de livraison.\n\n"
        f"ACTION : Alerter le responsable supply chain immédiatement.\n"
        f"Activer le plan de continuité d'approvisionnement."
    )

    reco = "Escalade supply chain immédiate. Plan de continuité à activer."
    return court, detail, reco


def build_message_process(rule: dict, ctx: dict) -> tuple[str, str, str]:
    kpi_label = {
        'isp_bas'     : 'Indice de Stabilité Process',
        'trs_critique': 'TRS',
        'derive_cycle': 'Dérive Temps de Cycle',
    }.get(rule.get('rule_name', ''), 'KPI Process')

    valeur_str = (
        f"{ctx['valeur']*100:.1f}%"
        if ctx['valeur'] <= 1.0 else f"{ctx['valeur']:.1f}"
    )
    seuil_str = (
        f"{ctx['seuil']*100:.1f}%"
        if ctx['seuil'] <= 1.0 else f"{ctx['seuil']:.1f}"
    )

    court = (
        f"{rule.get('label', kpi_label).upper()} — "
        f"{ctx['usine_label']} · {valeur_str}"
    )

    detail = (
        f"PROBLÈME : {kpi_label} à {valeur_str} "
        f"(seuil : {seuil_str}).\n\n"
        f"CONTEXTE : Machine : {ctx['machine_id']}. "
        f"Pièce : {ctx['type_piece']}. "
        f"Équipe : {ctx['equipe']}.\n"
        f"Problème dominant sur cette usine : "
        f"{ctx['dominant_problem']}.\n\n"
        f"IMPACT : Performance industrielle dégradée.\n\n"
        f"ACTION : {rule.get('message', 'Analyser les causes racines.')}"
    )

    reco = rule.get('message', 'Analyse root-cause requise.')
    return court, detail, reco


def build_message_resolved(
    rule: dict,
    ctx: dict
) -> tuple[str, str, str]:
    duree = ctx.get('duree_incident_min', 0.0)
    duree_str = (
        f"{int(duree)//60}h{int(duree)%60:02d}"
        if duree >= 60 else f"{duree:.0f} min"
    )

    court = (
        f"RÉSOLU — {rule.get('label', rule.get('rule_name', 'Alerte'))} "
        f"· {ctx['usine_label']} · Durée : {duree_str}"
    )

    detail = (
        f"L'alerte '{rule.get('label', '')}' sur {ctx['usine_label']} "
        f"est résolue.\n"
        f"Durée totale de l'incident : {duree_str}.\n"
        f"Retour à la normale confirmé.\n"
        f"Surveillance maintenue."
    )

    return court, detail, ""


# ─────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────

def evaluate_tick() -> None:
    """
    Évalue toutes les règles d'alerte pour toutes les usines.
    Appelé par simulator._tick_loop() à chaque tick,
    après kpi_engine.process_tick().

    Séquence :
      Pour chaque usine :
        Lire l'état courant
        Pour chaque règle dans ALERT_RULES :
          Évaluer la règle
    """
    for usine_id in USINES:
        state = store.get_current_state(usine_id)

        if state.get('statut_global') == 'INIT':
            continue

        for rule_name, rule in ALERT_RULES.items():
            try:
                # Injecter rule_name dans le dict rule pour les dispatchers
                rule_avec_nom = {**rule, 'rule_name': rule_name}
                _evaluate_rule(
                    usine_id, rule_name, rule_avec_nom, state
                )
            except Exception as e:
                print(
                    f"  ⚠ alert_engine · {usine_id} · "
                    f"{rule_name} : {e}"
                )


# ─────────────────────────────────────────────────────────────
# INITIALISATION AU CHARGEMENT
# ─────────────────────────────────────────────────────────────
_load_spc_limits()
print("✓ alert_engine.py chargé")
print(f"  Règles actives : {list(ALERT_RULES.keys())}")