# ============================================================
# app_groupe.py — MECHA · Vue groupe · Port 8050
#
# Vue d'ensemble des trois sites. Chaque fiche de site ouvre le
# tableau de bord de l'usine. L'habillage (thème, navigation,
# en-tête) vient de shell.py, commun aux quatre applications.
# ============================================================

import threading
import time

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go

import store
import kpi_engine
import simulator
import shell
from config import (
    USINES, USINE_LABELS, USINE_PORTS,
    USINE_DOMINANT_PROBLEM,
)

# ─────────────────────────────────────────────────────────────
# INITIALISATION DASH
# ─────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title='MECHA · Groupe',
    update_title=None,
    suppress_callback_exceptions=True,
)
server = app.server

# ─────────────────────────────────────────────────────────────
# SAFE SIMULATOR START
# ─────────────────────────────────────────────────────────────
_sim_started = False
_sim_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────
# ALERT MEMORY
# ─────────────────────────────────────────────────────────────
_ALERT_MEMORY = {}
_ALERT_TTL = {
    'CRITICAL': 30,
    'WARNING': 10,
    'INFO': 6,
}


def ensure_simulator_started():
    global _sim_started
    with _sim_lock:
        if not _sim_started:
            simulator.start()
            _sim_started = True


def _get_persistent_alerts(all_alerts):
    now = time.time()

    if all_alerts is not None and not all_alerts.empty:
        for _, row in all_alerts.iterrows():
            sev = row.get('severite', 'INFO')
            msg = _safe_text(row.get('message_court', ''))
            key = f"{sev}|{msg}"
            _ALERT_MEMORY[key] = {
                'timestamp': now,
                'severity': sev,
                'message': msg,
            }

    visible = []
    for key, item in list(_ALERT_MEMORY.items()):
        sev = item['severity']
        ttl = _ALERT_TTL.get(sev, 6)
        if now - item['timestamp'] <= ttl:
            visible.append(item)
        else:
            del _ALERT_MEMORY[key]

    priority = {'CRITICAL': 0, 'WARNING': 1, 'INFO': 2}
    visible.sort(key=lambda x: priority.get(x['severity'], 3))
    return visible


# ─────────────────────────────────────────────────────────────
# AIDES D'AFFICHAGE
# ─────────────────────────────────────────────────────────────
def _safe_text(value: str) -> str:
    if not value:
        return ""
    return " ".join(str(value).replace("_", " ").split())


def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f} %".replace('.', ',')


def _fmt_trs_color(trs: float, theme: dict) -> str:
    if trs >= 0.90:
        return theme['ok']
    if trs >= 0.80:
        return theme['warning']
    return theme['critical']


def _couleur_rebut(rebut: float, theme: dict) -> str:
    if rebut > 0.10:
        return theme['critical']
    if rebut > 0.05:
        return theme['warning']
    return theme['text_primary']


def _pluriel(n: int, singulier: str, pluriel: str) -> str:
    return f"{n} {singulier if n <= 1 else pluriel}"


# ─────────────────────────────────────────────────────────────
# BANDEAU D'ALERTE
# ─────────────────────────────────────────────────────────────
def build_alert_banner(persistent_alerts, theme: dict) -> html.Div:
    if not persistent_alerts:
        return html.Div()

    sev = persistent_alerts[0]['severity']
    couleur = {
        'CRITICAL': theme['critical'],
        'WARNING': theme['warning'],
    }.get(sev, theme['accent_blue'])
    messages = " · ".join(a['message'] for a in persistent_alerts[:3])

    return html.Div(
        className='alert-banner',
        role='status',
        style={'borderColor': shell.rgba(couleur, 0.30), 'background': shell.rgba(couleur, 0.06)},
        children=[
            html.Div('!', className='alert-icon',
                     style={'background': shell.rgba(couleur, 0.14), 'color': couleur}),
            html.Div(messages, className='alert-text'),
        ],
    )


# ─────────────────────────────────────────────────────────────
# CHIFFRES CLÉS DU GROUPE
# ─────────────────────────────────────────────────────────────
def build_exec_kpi_strip(summaries: list, critiques, theme: dict) -> html.Div:
    nb = max(len(summaries), 1)
    avg_trs = sum(s.get('TRS_courant', 0.0) for s in summaries) / nb
    avg_rebut = sum(s.get('taux_rebut', 0.0) for s in summaries) / nb
    total_alerts = sum(s.get('nb_alertes', 0) for s in summaries)
    nb_critiques = len([s for s in summaries if s.get('statut_global') == 'CRITICAL'])

    def chiffre(titre, valeur, detail, couleur):
        return html.Div(className='metric-card', children=[
            html.Div(titre, className='metric-title'),
            html.Div(valeur, className='metric-value', style={'color': couleur}),
            html.Div(detail, className='metric-sub'),
        ])

    return html.Div(className='kpi-strip', children=[
        chiffre('TRS du groupe', _fmt_pct(avg_trs),
                'Objectif 85 % · moyenne des sites', _fmt_trs_color(avg_trs, theme)),
        chiffre('Alertes actives', str(total_alerts),
                f"dont {_pluriel(len(critiques), 'critique', 'critiques')}",
                theme['critical'] if len(critiques) > 0 else theme['text_primary']),
        chiffre('Taux de rebut moyen', _fmt_pct(avg_rebut),
                'Seuil acceptable 5 %', _couleur_rebut(avg_rebut, theme)),
        chiffre('Sites en état critique', f"{nb_critiques} / {len(summaries)}",
                'À traiter en priorité' if nb_critiques else 'Aucun site à l’arrêt',
                theme['critical'] if nb_critiques else theme['ok']),
    ])


# ─────────────────────────────────────────────────────────────
# FICHE DE SITE
# ─────────────────────────────────────────────────────────────
def build_sparkline(trs_values: list, theme: dict) -> dcc.Graph:
    fig = go.Figure(go.Scatter(
        y=trs_values or [0.0],
        mode='lines',
        line=dict(color=theme['accent_blue'], width=1.6),
        fill='tozeroy',
        fillcolor=theme['chart_fill'],
        hoverinfo='skip',
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=2, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, range=[0, 1.05]),
        showlegend=False,
        height=48,
    )
    return dcc.Graph(
        figure=fig,
        config={'displayModeBar': False, 'staticPlot': True},
        style={'height': '48px'},
    )


def build_dpq_bars(d: float, p: float, q: float, theme: dict) -> html.Div:
    """Décomposition du TRS : disponibilité × performance × qualité."""
    rows = []
    for libelle, val in [('Disponibilité', d), ('Performance', p), ('Qualité', q)]:
        couleur = _fmt_trs_color(val, theme)
        rows.append(html.Div(className='bar-row', children=[
            html.Div(libelle, className='bar-label'),
            html.Div(className='bar-track', children=[
                html.Div(className='bar-fill',
                         style={'width': f"{max(0, min(val, 1)) * 100:.0f}%", 'background': couleur}),
            ]),
            html.Div(f"{val * 100:.0f} %", className='bar-value'),
        ]))
    return html.Div(children=rows)


def build_usine_card(summary: dict, trend_data: dict, theme: dict) -> html.A:
    """Fiche d'un site. Toute la fiche est un lien vers le tableau de bord de l'usine."""
    usine_id = summary['usine_id']
    statut = summary.get('statut_global', 'INIT')
    sc = shell.statut_config(statut, theme)

    trs = summary.get('TRS_courant', 0.0)
    rebut = summary.get('taux_rebut', 0.0)
    nb_alert = summary.get('nb_alertes', 0)
    aggs = store.get_aggregations(usine_id).get('1h', {})

    libelle = _safe_text(USINE_LABELS.get(usine_id, usine_id))
    nom = libelle.split('—')[0].strip()

    return html.A(
        href=shell.url_site(USINE_PORTS[usine_id]),
        title=f"Ouvrir le tableau de bord de {libelle}",
        children=[html.Div(className='usine-card', children=[
            html.Div(className='usine-status-line', style={'background': sc['dot']}),

            html.Div(className='card-top', children=[
                html.Div(children=[
                    html.Div(libelle, className='site-name'),
                    html.Div(_safe_text(USINE_DOMINANT_PROBLEM.get(usine_id, '')),
                             className='site-problem'),
                ]),
                shell.etat(statut, theme),
            ]),

            html.Div(children=[
                html.Div(className='trs-ligne', children=[
                    html.Div(_fmt_pct(trs), className='trs-value',
                             style={'color': _fmt_trs_color(trs, theme)}),
                    html.Div('TRS', className='trs-label'),
                ]),
                html.Div(f"Moyenne sur 1 h : {_fmt_pct(summary.get('TRS_moyen_1h', 0.0))}",
                         className='trs-meta'),
            ]),

            build_dpq_bars(aggs.get('disponibilite', 0.0), aggs.get('performance', 0.0),
                           aggs.get('qualite', 0.0), theme),

            html.Div(children=[
                html.Div('Tendance du TRS · 48 dernières sessions', className='section-caption'),
                build_sparkline(trend_data.get('trs_values', []), theme),
            ]),

            html.Div(className='mini-grid', children=[
                html.Div(className='mini-stat', children=[
                    html.Div('Taux de rebut', className='mini-label'),
                    html.Div(_fmt_pct(rebut), className='mini-value',
                             style={'color': _couleur_rebut(rebut, theme)}),
                ]),
                html.Div(className='mini-stat', children=[
                    html.Div('Alertes actives', className='mini-label'),
                    html.Div(str(nb_alert), className='mini-value',
                             style={'color': theme['critical'] if nb_alert > 0 else theme['text_primary']}),
                ]),
            ]),

            html.Div(className='lien-action', children=[
                html.Span(f"Ouvrir {nom}"),
                html.Span('→'),
            ]),
        ])],
    )


# ─────────────────────────────────────────────────────────────
# CLASSEMENT ET POINTS D'ATTENTION
# ─────────────────────────────────────────────────────────────
def build_comparison_table(summaries: list, theme: dict) -> html.Div:
    ranked = sorted(summaries, key=lambda s: s.get('TRS_moyen_1h', 0.0), reverse=True)

    rows = []
    for rang, s in enumerate(ranked, start=1):
        agg = store.get_aggregations(s['usine_id']).get('1h', {})
        trs_1h = agg.get('TRS_moyen', 0.0)
        trs_now = s.get('TRS_courant', 0.0)
        rebut_1h = agg.get('rebut_moyen', 0.0)
        nb_alert = s.get('nb_alertes', 0)
        sc = shell.statut_config(s.get('statut_global', 'INIT'), theme)

        rows.append(html.Tr(children=[
            html.Td(html.A(
                href=shell.url_site(USINE_PORTS[s['usine_id']]),
                children=[
                    html.Span(str(rang), className='rang'),
                    html.Span(className='andon', style={'background': sc['dot']}),
                    html.Span(_safe_text(USINE_LABELS.get(s['usine_id'], s['usine_id']))),
                ],
            )),
            html.Td(_fmt_pct(trs_1h), style={'color': _fmt_trs_color(trs_1h, theme)}),
            html.Td(_fmt_pct(trs_now), style={'color': _fmt_trs_color(trs_now, theme)}),
            html.Td(_fmt_pct(rebut_1h), style={'color': _couleur_rebut(rebut_1h, theme)}),
            html.Td(str(nb_alert),
                    style={'color': theme['critical'] if nb_alert > 0 else theme['text_muted']}),
        ]))

    return html.Div(className='panel', children=[
        html.Div(className='panel-head', children=[
            html.Div(children=[
                html.Div('Classement des sites', className='panel-title'),
                html.Div('Du meilleur TRS au plus faible, sur la dernière heure',
                         className='panel-subtitle'),
            ]),
        ]),
        html.Table(className='compare-table', children=[
            html.Thead(html.Tr([
                html.Th('Site'), html.Th('TRS sur 1 h'), html.Th('TRS actuel'),
                html.Th('Rebut sur 1 h'), html.Th('Alertes'),
            ])),
            html.Tbody(rows),
        ]),
    ])


def build_attention_panel(summaries: list, persistent_alerts: list, theme: dict) -> html.Div:
    """Ce qu'il faut regarder en premier : site le plus faible, alertes en cours."""
    ranked = sorted(summaries, key=lambda x: x.get('TRS_moyen_1h', 0.0), reverse=True)

    def ligne(titre, valeur, detail, couleur=None):
        return html.Div(className='attention-ligne', children=[
            html.Div(titre, className='attention-titre'),
            html.Div(valeur, className='attention-valeur',
                     style={'color': couleur} if couleur else None),
            html.Div(detail, className='attention-detail'),
        ])

    lignes = []
    if ranked:
        pire, meilleur = ranked[-1], ranked[0]
        lignes.append(ligne(
            'Site à surveiller',
            _safe_text(USINE_LABELS.get(pire['usine_id'], pire['usine_id'])),
            f"TRS sur 1 h : {_fmt_pct(pire.get('TRS_moyen_1h', 0.0))} · "
            f"{_safe_text(USINE_DOMINANT_PROBLEM.get(pire['usine_id'], ''))}",
            shell.statut_config(pire.get('statut_global', 'INIT'), theme)['color'],
        ))
        lignes.append(ligne(
            'Meilleur site',
            _safe_text(USINE_LABELS.get(meilleur['usine_id'], meilleur['usine_id'])),
            f"TRS sur 1 h : {_fmt_pct(meilleur.get('TRS_moyen_1h', 0.0))}",
        ))

    if persistent_alerts:
        for alerte in persistent_alerts[:3]:
            couleur = theme['critical'] if alerte['severity'] == 'CRITICAL' else theme['warning']
            lignes.append(ligne(
                'Alerte critique' if alerte['severity'] == 'CRITICAL' else 'Alerte',
                alerte['message'], '', couleur,
            ))
    else:
        lignes.append(ligne('Alertes', 'Aucune alerte en cours', ''))

    return html.Div(className='panel', children=[
        html.Div(className='panel-head', children=[
            html.Div('À regarder en premier', className='panel-title'),
        ]),
        html.Div(className='attention', children=lignes),
    ])


# ─────────────────────────────────────────────────────────────
# MISE EN PAGE
# ─────────────────────────────────────────────────────────────
app.layout = shell.racine([
    dcc.Interval(id='interval', interval=1000, n_intervals=0),
    html.Div(id='page-content'),
])


@app.callback(
    Output('page-content', 'children'),
    Input('interval', 'n_intervals'),
)
def update_page(n):
    ensure_simulator_started()

    theme = shell.theme()
    summaries = kpi_engine.get_usine_summary()
    for s in summaries:
        s['TRS_moyen_1h'] = store.get_aggregations(s['usine_id']).get('1h', {}).get('TRS_moyen', 0.0)

    ts_str = '—'
    for usine_id in USINES:
        ts = store.get_sim_state(usine_id).get('timestamp_simule')
        if ts and hasattr(ts, 'strftime'):
            ts_str = ts.strftime('%d/%m/%Y · %H:%M')
            break

    all_alerts = store.get_active_alerts()
    critiques = all_alerts[all_alerts['severite'] == 'CRITICAL'] if not all_alerts.empty else all_alerts
    persistent_alerts = _get_persistent_alerts(all_alerts)
    trends = {u: kpi_engine.get_trs_trend(u, n_sessions=48) for u in USINES}

    nb_critiques = len([s for s in summaries if s.get('statut_global') == 'CRITICAL'])
    nb_surveiller = len([s for s in summaries if s.get('statut_global') == 'WARNING'])
    if nb_critiques:
        constat = f"{_pluriel(nb_critiques, 'site en état critique', 'sites en état critique')}"
    elif nb_surveiller:
        constat = f"{_pluriel(nb_surveiller, 'site à surveiller', 'sites à surveiller')}"
    else:
        constat = 'tous les sites fonctionnent normalement'

    return [
        shell.navigation('groupe'),
        html.Main(className='page-wrap', children=[
            shell.entete(
                'Vue d’ensemble du groupe',
                f"{len(summaries)} sites suivis · {constat}. Cliquez sur un site pour ouvrir son tableau de bord.",
                ts_str,
            ),
            build_alert_banner(persistent_alerts, theme),
            build_exec_kpi_strip(summaries, critiques, theme),
            html.Div(className='usines-grid', children=[
                build_usine_card(s, trends[s['usine_id']], theme) for s in summaries
            ]),
            html.Div(className='content-grid', children=[
                build_comparison_table(summaries, theme),
                build_attention_panel(summaries, persistent_alerts, theme),
            ]),
            shell.pied('MECHA · Supervision de production · MSPR TPRE841 · données simulées'),
        ]),
    ]


# ─────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    ensure_simulator_started()
    app.run(debug=False, port=shell.PORT_GROUPE, host='0.0.0.0')
