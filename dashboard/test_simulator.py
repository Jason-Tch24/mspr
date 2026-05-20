# test_simulator.py
import time
import store
import simulator

print("=== TEST SIMULATEUR ===\n")

# Démarre la simulation
simulator.start()

# Attendre 3 ticks
print("\nAttente 4 secondes (3 à 4 ticks)...")
time.sleep(4)

# Vérifier que le store est alimenté
for usine in ['Usine_A', 'Usine_B', 'Usine_C']:
    state = store.get_current_state(usine)
    buf   = store.get_buffer(usine)

    assert state['TRS'] > 0, f"TRS nul pour {usine}"
    assert len(buf) > 0,     f"Buffer vide pour {usine}"

    print(f"✓ {usine}")
    print(f"  TRS courant   : {state['TRS']:.3f}")
    print(f"  Rebut courant : {state['taux_rebut']*100:.2f}%")
    print(f"  Sessions buf  : {len(buf)}")
    print(f"  Timestamp sim : {state['timestamp']}")
    print()

# Progression
prog = simulator.get_progress()
for usine, p in prog.items():
    print(f"  {usine} · progression : {p['progression_pct']}%")

simulator.stop()
print("\n✓ simulator.py validé — prêt pour kpi_engine.py")