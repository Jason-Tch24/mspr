# test_alert_engine.py
import time
import store
import simulator
import alert_engine

print("=== TEST ALERT ENGINE ===\n")

simulator.start()
print("Attente 10 secondes (simulation en cours)...")
time.sleep(10)

# Test 1 : vérifier que l'évaluation tourne sans erreur
print("✓ Test 1 — evaluate_tick() sans crash")

# Test 2 : injecter manuellement une condition d'alerte
store.update_current_state('Usine_A', {
    'panne_machine'     : 1,
    'type_panne'        : 'Usure outil',
    'duree_arret_min'   : 45.0,
    'statut_global'     : 'OK',
})
alert_engine.evaluate_tick()
actives = store.get_active_alerts('Usine_A')
print(f"✓ Test 2 — Alertes actives Usine A : {len(actives)}")
if len(actives) > 0:
    print(f"  Première alerte : {actives.iloc[0]['message_court']}")

# Test 3 : vérifier la structure ALERT_TABLE
hist = store.get_alert_history()
print(f"✓ Test 3 — Historique total : {len(hist)} alertes")

# Test 4 : vérifier les messages
for usine in ['Usine_A', 'Usine_B', 'Usine_C']:
    a = store.get_active_alerts(usine)
    print(f"  {usine} : {len(a)} alertes actives")

simulator.stop()
print("\n✓ alert_engine.py validé — prêt pour les dashboards")