# ============================================================
# shell.py — Habillage commun aux quatre tableaux de bord MECHA
#
# Une seule définition du thème, de la navigation, de l'en-tête
# de page et de la barre d'onglets. Les quatre applications
# (groupe, usines A, B, C) l'importent : elles se présentent
# ainsi comme un seul outil, avec la même navigation partout.
# ============================================================

from dash import html
from flask import has_request_context, request

import store
from config import USINES, USINE_LABELS, USINE_PORTS

PORT_GROUPE = 8050

FONT = '"IBM Plex Sans", "Segoe UI", system-ui, -apple-system, sans-serif'
FONT_MONO = '"IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace'

# ─────────────────────────────────────────────────────────────
# THÈME — fiche d'atelier : papier clair, encre bleu nuit,
# un seul accent (bleu de traçage), couleurs d'andon pour l'état.
# Mêmes teintes que le support de soutenance.
# ─────────────────────────────────────────────────────────────
THEME = {
    'mode'           : 'light',
    # surfaces
    'bg_primary'     : '#F4F2ED',   # papier
    'bg_secondary'   : '#EEEBE4',
    'bg_card'        : '#FFFFFF',   # fiche
    'bg_surface'     : '#F8F7F3',   # creux
    'bg_sidebar'     : '#F4F2ED',
    'glass'          : '#F8F7F3',
    # encre
    'text_primary'   : '#14213D',
    'text_secondary' : '#45505F',
    'text_muted'     : '#6B7483',
    'border'         : 'rgba(20,33,61,0.12)',
    # accent unique + neutres
    'accent_blue'    : '#1F6F78',
    'accent_cyan'    : '#1F6F78',
    'accent_purple'  : '#45505F',
    'accent_green'   : '#2E7D4F',
    'accent_orange'  : '#B84A0E',
    # andon
    'ok'             : '#2E7D4F',
    'warning'        : '#B26A00',
    'critical'       : '#B3261E',
    'info'           : '#1F6F78',
    # graphiques
    'chart_grid'     : '#E9E5DC',
    'chart_line'     : '#1F6F78',
    'chart_fill'     : 'rgba(31,111,120,0.10)',
    'ucl_color'      : '#B3261E',
    'lcl_color'      : '#B3261E',
    'uwl_color'      : '#B26A00',
    'paper_bgcolor'  : '#FFFFFF',
    'plot_bgcolor'   : '#FFFFFF',
    'font_color'     : '#45505F',
}


def theme(_mode: str | None = None) -> dict:
    """Thème unique de l'application (le paramètre est conservé par compatibilité)."""
    return dict(THEME)


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return f'rgba(20,33,61,{alpha})'
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def theme_vars(t: dict | None = None) -> dict:
    """Variables CSS lues par assets/app.css."""
    t = t or THEME
    return {
        '--papier'   : t['bg_primary'],
        '--fiche'    : t['bg_card'],
        '--creux'    : t['bg_surface'],
        '--encre'    : t['text_primary'],
        '--encre-2'  : t['text_secondary'],
        '--encre-3'  : t['text_muted'],
        '--filet'    : t['border'],
        '--tracage'  : t['accent_blue'],
        '--andon-ok' : t['ok'],
        '--andon-alerte': t['warning'],
        '--andon-arret' : t['critical'],
    }


# ─────────────────────────────────────────────────────────────
# ÉTAT (andon)
# ─────────────────────────────────────────────────────────────
_LIBELLES_STATUT = {
    'CRITICAL': 'Critique',
    'WARNING' : 'À surveiller',
    'OK'      : 'Normal',
    'INIT'    : 'Démarrage',
}


def statut_config(statut: str, t: dict | None = None) -> dict:
    t = t or THEME
    couleur = {
        'CRITICAL': t['critical'],
        'WARNING' : t['warning'],
        'OK'      : t['ok'],
    }.get(statut, t['text_muted'])
    return {
        'color' : couleur,
        'dot'   : couleur,
        'bg'    : rgba(couleur, 0.08),
        'border': rgba(couleur, 0.30),
        'label' : _LIBELLES_STATUT.get(statut, str(statut).replace('_', ' ').capitalize()),
    }


def etat(statut: str, t: dict | None = None) -> html.Span:
    """Pastille d'état : point d'andon + libellé."""
    sc = statut_config(statut, t)
    return html.Span(className='etat', style={
        'color': sc['color'], 'borderColor': sc['border'], 'background': sc['bg'],
    }, children=[
        html.Span(className='andon', style={'background': sc['dot']}),
        sc['label'],
    ])


# ─────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────
def url_site(port: int) -> str:
    """Adresse d'un tableau de bord, sur l'hôte par lequel la page est consultée."""
    hote = 'localhost'
    if has_request_context():
        hote = request.host.split(':')[0] or hote
    return f'http://{hote}:{port}'


def _nom_court(usine_id: str) -> tuple[str, str]:
    """'Usine A — Lyon' → ('Usine A', 'Lyon')."""
    libelle = USINE_LABELS.get(usine_id, usine_id)
    nom, _, ville = libelle.partition('—')
    return nom.strip(), ville.strip()


def navigation(actif: str) -> html.Header:
    """Barre de navigation commune. `actif` vaut 'groupe' ou un identifiant d'usine."""
    liens = [html.A(
        'Groupe',
        href=url_site(PORT_GROUPE),
        className='nav-link active' if actif == 'groupe' else 'nav-link',
    )]
    for usine_id in USINES:
        nom, ville = _nom_court(usine_id)
        statut = store.get_current_state(usine_id).get('statut_global', 'INIT')
        sc = statut_config(statut)
        liens.append(html.A(
            href=url_site(USINE_PORTS[usine_id]),
            className='nav-link active' if actif == usine_id else 'nav-link',
            title=f'{nom} · {sc["label"]}',
            children=[
                html.Span(className='andon', style={'background': sc['dot']}),
                html.Span(nom),
                html.Span(ville, className='nav-ville'),
            ],
        ))
    return html.Header(className='nav', children=[
        html.A(href=url_site(PORT_GROUPE), className='nav-marque', children=[
            html.Span('MECHA', className='nav-marque-nom'),
            html.Span('Supervision de production', className='nav-marque-sous'),
        ]),
        html.Nav(className='nav-links', children=liens),
    ])


# ─────────────────────────────────────────────────────────────
# EN-TÊTE DE PAGE
# ─────────────────────────────────────────────────────────────
def entete(titre: str, sous_titre: str, ts_str: str, statut: str | None = None) -> html.Div:
    droite = []
    if statut is not None:
        droite.append(etat(statut))
    droite.append(html.Span(className='entete-meta', children=[
        html.Span(className='pouls'),
        f'Simulation en cours · {ts_str}',
    ]))
    return html.Div(className='entete', children=[
        html.Div(children=[
            html.H1(titre, className='entete-titre'),
            html.P(sous_titre, className='entete-sous'),
        ]),
        html.Div(className='entete-droite', children=droite),
    ])


# ─────────────────────────────────────────────────────────────
# ONGLETS
# ─────────────────────────────────────────────────────────────
def barre_onglets(onglets: list[tuple[str, str, str]], actif: str) -> html.Div:
    """onglets : liste de (libellé, identifiant d'onglet, identifiant du bouton)."""
    return html.Div(className='onglets', role='tablist', children=[
        html.Button(
            libelle, id=id_bouton, n_clicks=0, role='tab',
            className='onglet actif' if actif == id_onglet else 'onglet',
        )
        for libelle, id_onglet, id_bouton in onglets
    ])


def pied(texte: str) -> html.Div:
    return html.Div(texte, className='footer-note')


def racine(children: list, id_racine: str = 'root') -> html.Div:
    """Conteneur racine statique : porte les variables CSS du thème."""
    return html.Div(id=id_racine, className='theme-root', style=theme_vars(), children=children)
