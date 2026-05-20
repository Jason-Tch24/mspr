# test_kpi_engine.py
import time
import store
import simulator
import kpi_engine

print("=== TEST KPI ENGINE ===\n")

simulator.start()
print("Attente 5 secondes...")
time.sleep(5)

for usine in ['Usine_A', 'Usine_B', 'Usine_C']:
    aggs  = store.get_aggregations(usine)
    state = store.get_current_state(usine)
    mach  = store.get_machine_states(usine)

    assert aggs['1h']['nb_sessions'] > 0,  f"Pas de sessions 1h pour {usine}"
    assert state['statut_global'] in ('OK','WARNING','CRITICAL','INIT')

    print(f"✓ {usine}")
    print(f"  TRS moyen 1h   : {aggs['1h']['TRS_moyen']*100:.1f}%")
    print(f"  TRS moyen 8h   : {aggs['8h']['TRS_moyen']*100:.1f}%")
    print(f"  Rebut moyen 1h : {aggs['1h']['rebut_moyen']*100:.2f}%")
    print(f"  Statut global  : {state['statut_global']}")
    print(f"  Machine active : {state['machine_id']} → {mach[state['machine_id']]['statut']}")
    print()

trend = kpi_engine.get_trs_trend('Usine_A', n_sessions=10)
assert len(trend['trs_values']) > 0
print(f"✓ get_trs_trend OK — {len(trend['trs_values'])} points")

summary = kpi_engine.get_usine_summary()
assert len(summary) == 3
print(f"✓ get_usine_summary OK — {len(summary)} usines")

simulator.stop()
print("\n✓ kpi_engine.py validé — prêt pour alert_engine.py")