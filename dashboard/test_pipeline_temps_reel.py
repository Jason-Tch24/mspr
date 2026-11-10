"""
Tests d'intégration du pipeline temps réel :
simulateur (rejeu des données Gold) → store → moteur KPI → moteur d'alertes.
"""

import alert_engine
import config
import kpi_engine
import store


def test_simulateur_alimente_le_store(simulateur):
    for usine in config.USINES:
        etat = store.get_current_state(usine)
        assert len(store.get_buffer(usine)) > 0, f"Buffer vide pour {usine}"
        assert etat['timestamp'] is not None
        assert 0 <= etat['TRS'] <= 1


def test_simulateur_progression(simulateur):
    for usine, p in simulateur.get_progress().items():
        assert p['sessions_totales'] > 0
        assert p['session_courante'] > 0, f"{usine} n'avance pas"


def test_agregations_kpi_calculees(simulateur):
    for usine in config.USINES:
        aggs = store.get_aggregations(usine)
        assert aggs['1h']['nb_sessions'] > 0, f"Pas de sessions 1h pour {usine}"
        assert 0 <= aggs['1h']['TRS_moyen'] <= 1
        assert store.get_current_state(usine)['statut_global'] in ('OK', 'WARNING', 'CRITICAL', 'INIT')


def test_tendance_trs_et_synthese_groupe(simulateur):
    tendance = kpi_engine.get_trs_trend('Usine_A', n_sessions=10)
    assert len(tendance['trs_values']) > 0
    assert len(kpi_engine.get_usine_summary()) == len(config.USINES)


def test_moteur_alertes_sans_erreur(simulateur):
    alert_engine.evaluate_tick()
    historique = store.get_alert_history()
    assert set(historique['severite'].unique()) <= {'INFO', 'WARNING', 'CRITICAL'}


def test_panne_injectee_declenche_une_alerte(simulateur):
    store.inject_fault('Usine_A', {
        'panne_machine': 1, 'type_panne': 'Usure outil',
        'duree_arret_min': 45.0, 'disponibilite': 0.0, 'TRS': 0.0,
    })
    try:
        for _ in range(6):   # couvre la persistance exigée par les règles
            alert_engine.evaluate_tick()
        actives = store.get_active_alerts('Usine_A')
    finally:
        store.clear_fault('Usine_A')
    assert len(actives) >= 1, "Une panne machine doit produire au moins une alerte active"
