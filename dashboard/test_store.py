# test_store.py — à lancer depuis le dossier dashboard
import store

# Test 1 : écriture et lecture current state
store.update_current_state('Usine_A', {'TRS': 0.92, 'taux_rebut': 0.04})
state = store.get_current_state('Usine_A')
assert state['TRS'] == 0.92
print("✓ Test 1 PASSED — current state OK")

# Test 2 : buffer
store.push_to_buffer('Usine_A', {'TRS': 0.91, 'timestamp': '2024-01-01'})
store.push_to_buffer('Usine_A', {'TRS': 0.93, 'timestamp': '2024-01-02'})
df = store.get_buffer_as_df('Usine_A')
assert len(df) == 2
print("✓ Test 2 PASSED — buffer OK")

# Test 3 : alerte
from datetime import datetime
store.append_alert({
    'alert_id'        : 'test_001',
    'timestamp_debut' : datetime.utcnow(),
    'timestamp_fin'   : None,
    'usine_id'        : 'Usine_A',
    'machine_id'      : 'M01',
    'rule_name'       : 'derive_qualite',
    'label'           : 'Dérive Qualité',
    'kpi'             : 'taux_rebut',
    'valeur_observee' : 0.12,
    'seuil_franchi'   : 0.09,
    'type_seuil'      : 'UCL',
    'severite'        : 'WARNING',
    'statut'          : 'ACTIVE',
    'message_court'   : 'Taux de rebut > UCL',
    'message_detail'  : 'Test alerte',
    'acquittee'       : False,
    'duree_active_min': None,
})
actives = store.get_active_alerts('Usine_A')
assert len(actives) == 1
print("✓ Test 3 PASSED — alertes OK")

print("\n✓ store.py validé — prêt pour simulator.py")