"""Tests unitaires du store (état partagé en mémoire) — y compris l'injection de pannes."""

from datetime import datetime

import store


def test_ecriture_lecture_etat_courant():
    store.update_current_state('Usine_A', {'TRS': 0.92, 'taux_rebut': 0.04})
    etat = store.get_current_state('Usine_A')
    assert etat['TRS'] == 0.92
    assert etat['taux_rebut'] == 0.04


def test_buffer_ajoute_les_sessions():
    avant = len(store.get_buffer_as_df('Usine_C'))
    store.push_to_buffer('Usine_C', {'TRS': 0.91, 'timestamp': '2024-01-01'})
    store.push_to_buffer('Usine_C', {'TRS': 0.93, 'timestamp': '2024-01-02'})
    assert len(store.get_buffer_as_df('Usine_C')) == avant + 2


def test_alerte_active_retrouvee():
    store.append_alert({
        'alert_id': 'test_store_001', 'timestamp_debut': datetime.utcnow(),
        'timestamp_fin': None, 'usine_id': 'Usine_A', 'machine_id': 'M01',
        'rule_name': 'derive_qualite', 'label': 'Dérive Qualité', 'kpi': 'taux_rebut',
        'valeur_observee': 0.12, 'seuil_franchi': 0.09, 'type_seuil': 'UCL',
        'severite': 'WARNING', 'statut': 'ACTIVE', 'message_court': 'Taux de rebut > UCL',
        'message_detail': 'Test alerte', 'acquittee': False, 'duree_active_min': None,
    })
    actives = store.get_active_alerts('Usine_A')
    assert 'test_store_001' in set(actives['alert_id'])


def test_injection_de_panne_remplace_les_valeurs():
    store.update_current_state('Usine_B', {'temp_process_delta': 11.5})
    store.inject_fault('Usine_B', {'temp_process_delta': 7.6})
    try:
        assert store.get_current_state('Usine_B')['temp_process_delta'] == 7.6
        assert store.get_fault_injection('Usine_B') == {'temp_process_delta': 7.6}
    finally:
        store.clear_fault('Usine_B')
    assert store.get_current_state('Usine_B')['temp_process_delta'] == 11.5
    assert store.get_fault_injection('Usine_B') == {}


def test_injection_isolee_par_usine():
    store.inject_fault('Usine_A', {'usure_cumulee_pct': 92.0})
    try:
        assert store.get_fault_injection('Usine_B') == {}
    finally:
        store.clear_fault('Usine_A')
