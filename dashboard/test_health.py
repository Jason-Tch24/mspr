"""
test_health.py — Tests unitaires pytest pour les modules core du dashboard MECHA.

Ces tests sont au format pytest standard (fonctions def test_*) pour garantir
que pytest collecte au moins un item et retourne exit code 0 en CI.

Les fichiers test_store.py / test_simulator.py / test_kpi_engine.py /
test_alert_engine.py existants s'exécutent en tant que scripts au niveau
module pendant la phase de collection pytest — leurs assertions valident
également le comportement (toute erreur remonte comme CollectionError).
"""

import store
import config


# ── Config ────────────────────────────────────────────────────

def test_config_usines():
    assert len(config.USINES) == 3
    assert 'Usine_A' in config.USINES
    assert 'Usine_B' in config.USINES
    assert 'Usine_C' in config.USINES


def test_config_ports():
    assert config.USINE_PORTS['Usine_A'] == 8051
    assert config.USINE_PORTS['Usine_B'] == 8052
    assert config.USINE_PORTS['Usine_C'] == 8053


def test_config_seuils():
    assert 0 < config.TRS_SEUIL_CRITIQUE < config.TRS_SEUIL_ACCEPTABLE < 1
    assert 0 < config.USURE_SEUIL_WARNING < config.USURE_SEUIL_CRITIQUE <= 1


def test_config_alert_rules_non_vides():
    assert len(config.ALERT_RULES) > 0
    for rule_name, rule in config.ALERT_RULES.items():
        assert 'kpi'      in rule, f"Règle {rule_name} sans champ 'kpi'"
        assert 'severite' in rule, f"Règle {rule_name} sans champ 'severite'"
        assert rule['severite'] in ('INFO', 'WARNING', 'CRITICAL')


# ── Store — lecture / écriture ────────────────────────────────

def test_store_current_state_structure():
    state = store.get_current_state('Usine_A')
    assert isinstance(state, dict)
    for key in ('TRS', 'taux_rebut', 'statut_global', 'usure_cumulee_pct'):
        assert key in state, f"Clé manquante dans CURRENT_STATE : {key}"


def test_store_write_read():
    store.update_current_state('Usine_A', {'TRS': 0.88, 'taux_rebut': 0.03})
    state = store.get_current_state('Usine_A')
    assert state['TRS'] == 0.88
    assert state['taux_rebut'] == 0.03


def test_store_buffer_push_read():
    store.push_to_buffer('Usine_B', {'TRS': 0.90, 'timestamp': '2024-01-01'})
    df = store.get_buffer_as_df('Usine_B')
    assert len(df) >= 1
    assert 'TRS' in df.columns


def test_store_alert_append_and_query():
    from datetime import datetime
    store.append_alert({
        'alert_id'        : 'ci_test_001',
        'timestamp_debut' : datetime.utcnow(),
        'timestamp_fin'   : None,
        'usine_id'        : 'Usine_C',
        'machine_id'      : 'M01',
        'rule_name'       : 'trs_critique',
        'label'           : 'TRS Critique',
        'kpi'             : 'TRS',
        'valeur_observee' : 0.70,
        'seuil_franchi'   : 0.75,
        'type_seuil'      : 'FIXED',
        'severite'        : 'CRITICAL',
        'statut'          : 'ACTIVE',
        'message_court'   : 'TRS < 75%',
        'message_detail'  : 'Test CI',
        'acquittee'       : False,
        'duree_active_min': None,
    })
    actives = store.get_active_alerts('Usine_C')
    assert len(actives) >= 1
    assert actives.iloc[0]['severite'] == 'CRITICAL'


def test_store_aggregations_structure():
    aggs = store.get_aggregations('Usine_A')
    assert '1h' in aggs
    assert '8h' in aggs
    assert '24h' in aggs
    for fenetre in ('1h', '8h', '24h'):
        assert 'TRS_moyen' in aggs[fenetre]
        assert 'nb_pannes' in aggs[fenetre]


def test_store_machine_states_structure():
    machines = store.get_machine_states('Usine_A')
    for machine_id in config.MACHINES:
        assert machine_id in machines
        assert 'statut' in machines[machine_id]
        assert machines[machine_id]['statut'] in (
            'INIT', 'EN_PRODUCTION', 'ARRET', 'MAINTENANCE', 'STANDBY'
        )
