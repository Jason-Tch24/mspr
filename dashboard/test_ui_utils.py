"""Tests du filtre de clics des boutons d'injection de panne."""

from ui_utils import bouton_clique


def test_rafraichissement_sans_clic_ignore():
    triggered = [{'prop_id': 'fault-btn-surchauffe-B.n_clicks', 'value': 0},
                 {'prop_id': 'fault-btn-panne-B.n_clicks', 'value': 0},
                 {'prop_id': 'fault-btn-clear-B.n_clicks', 'value': 0}]
    assert bouton_clique(triggered) is None


def test_clic_reel_identifie():
    triggered = [{'prop_id': 'fault-btn-clear-B.n_clicks', 'value': 1}]
    assert bouton_clique(triggered) == 'fault-btn-clear-B'


def test_valeur_absente_ou_liste_vide():
    assert bouton_clique([{'prop_id': 'fault-btn-panne-B.n_clicks', 'value': None}]) is None
    assert bouton_clique([]) is None
    assert bouton_clique(None) is None
