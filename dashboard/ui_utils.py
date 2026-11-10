"""Utilitaires d'interface communs aux dashboards."""

from __future__ import annotations


def bouton_clique(triggered: list[dict]) -> str | None:
    """
    Identifiant du bouton réellement cliqué, ou None.

    Les boutons de l'onglet IA sont recréés à chaque rafraîchissement de
    l'écran. Dash déclenche alors le callback pour tous les boutons, avec
    n_clicks = 0 : sans ce filtre, une panne s'injectait toute seule à
    l'ouverture de l'onglet et « Reprendre simulateur » restait sans effet.
    Seul un déclencheur dont n_clicks est strictement positif est un clic.
    """
    for declencheur in triggered or []:
        if declencheur.get('value'):
            return declencheur['prop_id'].split('.')[0]
    return None
