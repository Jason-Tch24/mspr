# ============================================================
# app_usine_A.py — MECHA Site Dashboard · Usine A · Port 8051
#
# Problème dominant : Usure outil progressive
# Fix : tab-store en State dans update_page_A
#       tab bar dans callback séparé → onglet stable au refresh
# ============================================================

import threading
import time
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, ctx
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import requests

import config
import shell
import store
from ui_utils import bouton_clique
import kpi_engine
import simulator
from config import (
    USINES, USINE_LABELS, USINE_PORTS,
    USINE_DOMINANT_PROBLEM,
    get_theme,
    TRS_SEUIL_ACCEPTABLE, TRS_SEUIL_CRITIQUE,
    USURE_SEUIL_WARNING, USURE_SEUIL_CRITIQUE,
)

# ─────────────────────────────────────────────────────────────
# IDENTITY
# ─────────────────────────────────────────────────────────────
USINE_ID   = 'Usine_A'
PORT       = 8051
SITE_LABEL = USINE_LABELS[USINE_ID]
DOMINANT   = USINE_DOMINANT_PROBLEM[USINE_ID]

DEFAULT_THEME_MODE = 'light'

# ─────────────────────────────────────────────────────────────
# INITIALISATION DASH
# ─────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title=f'MECHA · {SITE_LABEL}',
    update_title=None,
    suppress_callback_exceptions=True,
)
server = app.server

# ─────────────────────────────────────────────────────────────
# SAFE SIMULATOR START
# ─────────────────────────────────────────────────────────────
_sim_started = False
_sim_lock    = threading.Lock()

def ensure_simulator_started():
    global _sim_started
    with _sim_lock:
        if not _sim_started:
            simulator.start()
            _sim_started = True

# ─────────────────────────────────────────────────────────────
# ALERT MEMORY
# ─────────────────────────────────────────────────────────────
_ALERT_MEMORY = {}
_ALERT_TTL    = {'CRITICAL': 30, 'WARNING': 10, 'INFO': 6}

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _safe_text(value) -> str:
    if not value: return ""
    txt = str(value).replace("_", " ").replace("—", "·").strip()
    while "  " in txt: txt = txt.replace("  ", " ")
    return txt

def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f} %".replace(".", ",")

def _fmt_trs_color(trs: float, theme: dict) -> str:
    if trs >= 0.90: return theme['ok']
    if trs >= 0.80: return theme['warning']
    return theme['critical']

def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    if len(h) != 6: return f'rgba(255,255,255,{alpha})'
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

def _soft_theme(mode: str | None = None) -> dict:
    return shell.theme()


def _statut_config(statut: str, theme: dict) -> dict:
    return shell.statut_config(statut, theme)


def _get_persistent_alerts(all_alerts):
    now = time.time()
    if all_alerts is not None and not all_alerts.empty:
        for _, row in all_alerts.iterrows():
            sev = row.get('severite', 'INFO')
            msg = _safe_text(row.get('message_court', ''))
            key = f"{sev}|{msg}"
            _ALERT_MEMORY[key] = {'sev': sev, 'msg': msg, 'ts': now}
    result, expired = [], []
    for key, data in _ALERT_MEMORY.items():
        age = now - data['ts']
        ttl = _ALERT_TTL.get(data['sev'], 6)
        if age <= ttl: result.append(data)
        else: expired.append(key)
    for k in expired: del _ALERT_MEMORY[k]
    result.sort(key=lambda x: {'CRITICAL': 0, 'WARNING': 1, 'INFO': 2}.get(x['sev'], 3))
    return result

# ─────────────────────────────────────────────────────────────
# PLOT HELPERS
# ─────────────────────────────────────────────────────────────

def _plot_layout(theme: dict, title: str = '', height: int = 280) -> dict:
    return dict(
        paper_bgcolor=theme.get('paper_bgcolor', theme['bg_card']),
        plot_bgcolor=theme.get('plot_bgcolor',  theme['bg_surface']),
        font=dict(family=shell.FONT, color=theme['text_muted'], size=12),
        margin=dict(l=40, r=16, t=36, b=32),
        height=height,
        title=dict(text=title,
                   font=dict(size=13, color=theme['text_secondary']),
                   x=0.0, xanchor='left', pad=dict(l=4)),
        showlegend=False,
        hovermode='x unified',
        hoverlabel=dict(bgcolor=theme['bg_surface'],
                        font_color=theme['text_primary'],
                        font_size=11, bordercolor=theme['border']),
    )

def _axis(theme: dict, title: str = '') -> dict:
    return dict(
        gridcolor=theme.get('chart_grid', theme['border']),
        linecolor=theme['border'],
        tickfont=dict(size=11, color=theme['text_muted']),
        title=dict(text=title, font=dict(size=11, color=theme['text_muted'])),
        showgrid=True, zeroline=False,
    )

# ─────────────────────────────────────────────────────────────
# COMPOSANTS SHELL
# ─────────────────────────────────────────────────────────────

def build_alert_banner(persistent_alerts: list, theme: dict) -> html.Div:
    if not persistent_alerts:
        return html.Div()
    top   = persistent_alerts[0]
    sev   = top['sev']
    color_map = {
        'CRITICAL': theme['critical'],
        'WARNING' : theme['warning'],
        'INFO'    : theme.get('accent_cyan', theme['accent_blue']),
    }
    color = color_map.get(sev, theme['text_muted'])
    icon  = {'CRITICAL': '!', 'WARNING': '!', 'INFO': 'i'}.get(sev, '·')
    extra = f"  +{len(persistent_alerts)-1} autres" if len(persistent_alerts) > 1 else ""
    return html.Div(className='alert-banner', style={
        'background': _rgba(color, 0.08), 'borderColor': _rgba(color, 0.22),
    }, children=[
        html.Div(icon, className='alert-icon',
                 style={'background': _rgba(color, 0.16), 'color': color}),
        html.Div(children=[
            html.Span(_safe_text(top['msg']),
                      style={'color': theme['text_primary'],
                             'fontWeight': '600', 'fontSize': '12px'}),
            html.Span(extra,
                      style={'color': theme['text_muted'], 'fontSize': '13px',
                             'marginLeft': '8px'}),
        ]),
    ])

# ─────────────────────────────────────────────────────────────
# KPI STRIP
# ─────────────────────────────────────────────────────────────

def build_kpi_strip(state: dict, aggs: dict, theme: dict) -> html.Div:
    trs      = state.get('TRS', 0.0)
    rebut    = state.get('taux_rebut', 0.0)
    usure    = state.get('usure_cumulee_pct', 0.0)
    energie  = state.get('consommation_kwh', 0.0)
    agg_1h   = aggs.get('1h', {})
    trs_1h   = agg_1h.get('TRS_moyen', 0.0)
    rebut_1h = agg_1h.get('rebut_moyen', 0.0)
    nb_pan   = agg_1h.get('nb_pannes', 0)

    def card(title, value_str, sub, color, bar_pct=None):
        children = [
            html.Div(title, className='metric-title'),
            html.Div(value_str, className='metric-value', style={'color': color}),
            html.Div(sub, className='metric-sub'),
        ]
        if bar_pct is not None:
            bc = (theme['critical'] if bar_pct > 90 else
                  theme['warning']  if bar_pct > 75 else theme['ok'])
            children.append(html.Div(className='metric-bar', children=[
                html.Div(className='metric-bar-fill',
                         style={'width': f'{min(bar_pct,100):.0f}%', 'background': bc})
            ]))
        return html.Div(className='metric-card', children=children)

    return html.Div(className='kpi-strip', children=[
        card('TRS actuel', _fmt_pct(trs),
             f'Moyenne 1 h · {_fmt_pct(trs_1h)}',
             _fmt_trs_color(trs, theme)),
        card('Taux de rebut', _fmt_pct(rebut),
             f'Moyenne 1 h · {_fmt_pct(rebut_1h)}',
             theme['critical'] if rebut > 0.08 else
             theme['warning']  if rebut > 0.05 else theme['ok']),
        card('Usure outil', f'{usure:.1f}%',
             f'{nb_pan} panne(s) sur 1 h',
             theme['critical'] if usure > 90 else
             theme['warning']  if usure > 75 else theme['text_primary'],
             usure),
        card('Énergie par session', f'{energie:.2f} kWh',
             'Session en cours', theme['accent_blue']),
    ])

# ─────────────────────────────────────────────────────────────
# MACHINE GRID
# ─────────────────────────────────────────────────────────────

def build_machine_grid(theme: dict) -> html.Div:
    machines = store.get_machine_states(USINE_ID)
    statut_labels = {
        'EN_PRODUCTION': ('En production',     theme['ok']),
        'ARRET':         ('À l’arrêt',     theme['critical']),
        'MAINTENANCE':   ('Maintenance', theme['warning']),
        'STANDBY':       ('En attente',     theme['text_muted']),
        'INIT':          ('Démarrage',        theme['text_muted']),
    }
    cards = []
    for m_id, m_state in machines.items():
        statut      = m_state.get('statut', 'INIT')
        label, color = statut_labels.get(statut, (statut, theme['text_muted']))
        usure       = m_state.get('usure_pct', 0.0)
        rebut       = m_state.get('taux_rebut', 0.0)
        u_color     = (theme['critical'] if usure > 90 else
                       theme['warning']  if usure > 75 else theme['ok'])
        cards.append(html.Div(style={
            'borderRadius': '14px', 'border': f"1px solid {theme['border']}",
            'background': theme['bg_surface'], 'padding': '14px',
        }, children=[
            html.Div(style={
                'display': 'flex', 'justifyContent': 'space-between',
                'alignItems': 'center', 'marginBottom': '10px',
            }, children=[
                html.Span(m_id, style={'fontWeight': '600', 'fontSize': '13px',
                                       'color': theme['text_primary']}),
                html.Span(label, style={
                    'fontSize': '12px', 'fontWeight': '600', 'color': color,
                    'padding': '2px 8px', 'borderRadius': '6px',
                    'border': f'1px solid {_rgba(color, 0.3)}',
                    'background': _rgba(color, 0.1),
                }),
            ]),
            html.Div(className='bar-row', children=[
                html.Span('Usure', className='bar-label'),
                html.Div(className='bar-track', children=[
                    html.Div(className='bar-fill',
                             style={'width': f'{min(usure,100):.0f}%',
                                    'background': u_color})
                ]),
                html.Span(f'{usure:.0f}%', className='bar-value'),
            ]),
            html.Div(f'Rebut · {rebut*100:.1f} %',
                     style={'marginTop': '6px', 'fontSize': '12px',
                            'color': theme['text_muted']}),
        ]))

    return html.Div(children=[
        html.Div('État des machines', style={
            'fontSize': '13px', 'fontWeight': '600',
            'color': theme['text_muted'], 'marginBottom': '10px',
        }),
        html.Div(style={
            'display': 'grid', 'gridTemplateColumns': 'repeat(2,1fr)', 'gap': '10px',
        }, children=cards),
    ])

# ─────────────────────────────────────────────────────────────
# GRAPHIQUES USINE A
# ─────────────────────────────────────────────────────────────

def build_trs_chart(theme: dict) -> dcc.Graph:
    import json
    from config import LIMITS_PATHS
    trend = kpi_engine.get_trs_trend(USINE_ID, n_sessions=96)
    ts    = trend.get('timestamps', [])
    vals  = trend.get('trs_values', [])
    ma    = trend.get('ma_values', [])
    try:
        with open(LIMITS_PATHS[USINE_ID]) as f:
            lim = json.load(f)
        ucl = lim.get('TRS', {}).get('ucl', 1.03)
        lcl = lim.get('TRS', {}).get('lcl', 0.86)
    except Exception:
        ucl, lcl = 1.03, 0.86

    fig = go.Figure()
    if vals:
        fig.add_trace(go.Scatter(
            x=ts, y=vals, mode='lines', name='TRS',
            line=dict(color=theme['accent_blue'], width=1.2),
            fill='tozeroy', fillcolor=theme['chart_fill'],
            hovertemplate='%{x|%d %b %H:%M}<br>TRS : %{y:.3f}<extra></extra>',
        ))
        if ma:
            fig.add_trace(go.Scatter(
                x=ts, y=ma, mode='lines', name='Moyenne mobile',
                line=dict(color=theme.get('accent_green', theme['ok']), width=2),
                hovertemplate='Moyenne mobile : %{y:.3f}<extra></extra>',
            ))
    fig.add_hline(y=lcl, line_dash='dot', line_color=theme['critical'], line_width=1,
                  annotation_text=f'LCL {lcl:.2f}',
                  annotation_font_size=9, annotation_font_color=theme['critical'],
                  annotation_position='bottom right')
    fig.add_hline(y=TRS_SEUIL_ACCEPTABLE, line_dash='dot',
                  line_color=theme['warning'], line_width=1,
                  annotation_text='Objectif 85 %',
                  annotation_font_size=9, annotation_font_color=theme['warning'],
                  annotation_position='top right')
    layout = _plot_layout(theme, 'TRS — évolution en temps réel', height=260)
    layout['xaxis']      = _axis(theme)
    layout['yaxis']      = {**_axis(theme, 'TRS'), 'range': [0.60, 1.05]}
    layout['showlegend'] = True
    layout['legend']     = dict(font=dict(size=11, color=theme['text_muted']),
                                bgcolor='rgba(0,0,0,0)', orientation='h', x=0, y=1.12)
    fig.update_layout(layout)
    return dcc.Graph(figure=fig, config={'displayModeBar': False})


def build_wear_scrap_chart(theme: dict) -> dcc.Graph:
    from plotly.subplots import make_subplots
    import json
    from config import LIMITS_PATHS
    trend_r = kpi_engine.get_rebut_trend(USINE_ID, n_sessions=96)
    ts      = trend_r.get('timestamps', [])
    rebut   = trend_r.get('rebut_values', [])
    usure   = trend_r.get('usure_values', [])
    try:
        with open(LIMITS_PATHS[USINE_ID]) as f:
            lim = json.load(f)
        ucl_r = lim.get('taux_rebut', {}).get('ucl', 0.09)
    except Exception:
        ucl_r = 0.09

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.55, 0.45], vertical_spacing=0.06)
    if rebut:
        fig.add_trace(go.Scatter(
            x=ts, y=rebut, mode='lines', name='Taux de rebut',
            line=dict(color=theme['critical'], width=1.4),
            fill='tozeroy', fillcolor=_rgba(theme['critical'], 0.07),
            hovertemplate='Rebut : %{y:.3f}<extra></extra>',
        ), row=1, col=1)
        fig.add_hline(y=ucl_r, line_dash='dot', line_color=theme['warning'],
                      line_width=1, row=1, col=1,
                      annotation_text=f'UCL {ucl_r:.3f}',
                      annotation_font_size=9, annotation_font_color=theme['warning'],
                      annotation_position='top right')
    if usure:
        fig.add_trace(go.Scatter(
            x=ts, y=usure, mode='lines', name='Usure outil (%)',
            line=dict(color=theme['warning'], width=1.4),
            fill='tozeroy', fillcolor=_rgba(theme['warning'], 0.07),
            hovertemplate='Usure : %{y:.1f}%<extra></extra>',
        ), row=2, col=1)
        fig.add_hline(y=USURE_SEUIL_CRITIQUE * 100, line_dash='dot',
                      line_color=theme['critical'], line_width=1, row=2, col=1,
                      annotation_text='Critique 90 %',
                      annotation_font_size=9, annotation_font_color=theme['critical'],
                      annotation_position='top right')
    layout = _plot_layout(theme, 'Taux de rebut et usure outil', height=320)
    layout['xaxis2']     = _axis(theme)
    layout['xaxis']      = _axis(theme)
    layout['yaxis']      = {**_axis(theme, 'Taux de rebut'), 'range': [0, max(ucl_r * 2.5, 0.15)]}
    layout['yaxis2']     = {**_axis(theme, 'Usure (%)'), 'range': [0, 105]}
    layout['showlegend'] = True
    layout['legend']     = dict(font=dict(size=11, color=theme['text_muted']),
                                bgcolor='rgba(0,0,0,0)', orientation='h', x=0, y=1.08)
    fig.update_layout(layout)
    return dcc.Graph(figure=fig, config={'displayModeBar': False})

# ─────────────────────────────────────────────────────────────
# ONGLETS
# ─────────────────────────────────────────────────────────────

def build_tab_overview(state: dict, aggs: dict, theme: dict) -> html.Div:
    return html.Div(style={
        'display': 'grid', 'gridTemplateColumns': '1.6fr 1fr',
        'gap': '16px', 'alignItems': 'start',
    }, children=[
        html.Div(children=[
            html.Div(className='panel', style={'marginBottom': '14px'}, children=[
                html.Div(className='panel-head', children=[
                    html.Div(children=[
                        html.Div('Suivi du TRS', className='panel-title'),
                        html.Div('TRS en temps réel et limites de contrôle statistique',
                                 className='panel-subtitle'),
                    ]),
                ]),
                html.Div(style={'padding': '0 16px 16px 16px'},
                         children=[build_trs_chart(theme)]),
            ]),
            html.Div(className='panel', children=[
                html.Div(className='panel-head', children=[
                    html.Div(children=[
                        html.Div('Taux de rebut et usure outil', className='panel-title'),
                        html.Div('Relation de cause à effet — signal principal de l’usine A',
                                 className='panel-subtitle'),
                    ]),
                ]),
                html.Div(style={'padding': '0 16px 16px 16px'},
                         children=[build_wear_scrap_chart(theme)]),
            ]),
        ]),
        html.Div(children=[
            html.Div(className='panel',
                     style={'padding': '16px', 'marginBottom': '14px'},
                     children=[build_machine_grid(theme)]),
            build_alerts_side(theme),
        ]),
    ])


def build_tab_maintenance(state: dict, theme: dict) -> html.Div:
    machines     = store.get_machine_states(USINE_ID)
    machine_id   = state.get('machine_id', 'N/A')
    remplacement = state.get('remplacement_outil', 0)
    nb_pannes_7j = state.get('nb_pannes_7j', 0)

    def gauge_usure(m_id, usure_pct):
        color = (theme['critical'] if usure_pct > 90 else
                 theme['warning']  if usure_pct > 75 else theme['ok'])
        fig = go.Figure(go.Indicator(
            mode='gauge+number', value=usure_pct,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': m_id,
                   'font': {'size': 13, 'color': theme['text_secondary']}},
            number={'suffix': '%', 'font': {'size': 20, 'color': color}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1,
                         'tickcolor': theme['text_muted'],
                         'tickfont': {'size': 10}},
                'bar': {'color': color, 'thickness': 0.22},
                'bgcolor': theme['bg_surface'], 'borderwidth': 0,
                'steps': [
                    {'range': [0,  75], 'color': _rgba(theme['ok'],       0.08)},
                    {'range': [75, 90], 'color': _rgba(theme['warning'],  0.12)},
                    {'range': [90,100], 'color': _rgba(theme['critical'], 0.16)},
                ],
                'threshold': {'line': {'color': theme['critical'], 'width': 2},
                              'thickness': 0.75, 'value': 90},
            }
        ))
        layout = _plot_layout(theme, height=180)
        layout['margin'] = dict(l=20, r=20, t=30, b=10)
        fig.update_layout(layout)
        return fig

    gauges = []
    for m_id, m_state in machines.items():
        u       = m_state.get('usure_pct', 0.0)
        est_h   = round((100 - u) / max(u, 1) * 2, 1) if u > 0 else 0
        c_est   = (theme['critical'] if u > 90 else
                   theme['warning']  if u > 75 else theme['ok'])
        gauges.append(html.Div(style={
            'borderRadius': '16px', 'border': f"1px solid {theme['border']}",
            'background': theme['bg_surface'], 'padding': '12px', 'textAlign': 'center',
        }, children=[
            dcc.Graph(figure=gauge_usure(m_id, u), config={'displayModeBar': False}),
            html.Div(f'Remplacement estimé dans ~{est_h} h',
                     style={'fontSize': '12px', 'color': c_est,
                            'fontWeight': '600', 'marginTop': '4px'}),
        ]))

    def stat_card(title, value, color):
        return html.Div(style={
            'borderRadius': '12px', 'border': f"1px solid {theme['border']}",
            'padding': '14px', 'background': theme['bg_surface'],
        }, children=[
            html.Div(title, style={'fontSize': '12px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(str(value), style={'fontSize': '22px', 'fontWeight': '600',
                                        'color': color, 'marginTop': '6px'}),
        ])

    return html.Div(children=[
        html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(4,1fr)',
                        'gap': '12px', 'marginBottom': '16px'}, children=gauges),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Synthèse maintenance', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(3,1fr)',
                            'gap': '10px'}, children=[
                stat_card('Machine active',          _safe_text(machine_id), theme['text_primary']),
                stat_card('Changements d’outil aujourd’hui', remplacement,           theme['accent_blue']),
                stat_card('Pannes sur 7 jours',    nb_pannes_7j,
                          theme['warning'] if nb_pannes_7j > 3 else theme['ok']),
            ]),
        ]),
    ])


def build_tab_quality(state: dict, theme: dict) -> html.Div:
    buf          = store.get_buffer_as_df(USINE_ID)
    taux_rebut   = state.get('taux_rebut', 0.0)
    pieces_rebut = state.get('pieces_rebutees', 0)
    type_piece   = state.get('type_piece', 'N/A')
    equipe       = state.get('equipe', 'N/A')
    rebut_color  = (theme['critical'] if taux_rebut > 0.08 else
                    theme['warning']  if taux_rebut > 0.05 else theme['ok'])

    rows = []
    if not buf.empty and 'type_piece' in buf.columns:
        grp = buf.groupby('type_piece')['taux_rebut'].mean().reset_index()
        for _, r in grp.iterrows():
            color = (theme['critical'] if r['taux_rebut'] > 0.10 else
                     theme['warning']  if r['taux_rebut'] > 0.05 else theme['ok'])
            rows.append(html.Tr([
                html.Td(_safe_text(r['type_piece']),
                        style={'padding': '8px 12px', 'fontSize': '12px',
                               'color': theme['text_primary'], 'fontWeight': '600'}),
                html.Td(f"{r['taux_rebut']*100:.2f}%",
                        style={'padding': '8px 12px', 'fontSize': '12px',
                               'color': color, 'fontWeight': '600', 'textAlign': 'right'}),
            ], style={'borderBottom': f"1px solid {theme['border']}"}))

    def summary_card(title, value, color):
        return html.Div(style={
            'borderRadius': '12px', 'border': f"1px solid {theme['border']}",
            'padding': '12px', 'background': theme['bg_surface'],
        }, children=[
            html.Div(title, style={'fontSize': '12px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(value, style={'fontSize': '26px', 'fontWeight': '600',
                                   'color': color, 'marginTop': '6px'}),
        ])

    return html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                            'gap': '16px'}, children=[
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Synthèse qualité', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(2,1fr)',
                            'gap': '10px', 'marginBottom': '12px'}, children=[
                summary_card('Taux de rebut',    f"{taux_rebut*100:.2f}%", rebut_color),
                summary_card('Pièces rebutées', str(pieces_rebut),       theme['text_primary']),
            ]),
            html.Div(
                f'Référence en cours : {_safe_text(type_piece)}  ·  Équipe : {_safe_text(equipe)}',
                style={'fontSize': '13px', 'color': theme['text_muted'], 'marginTop': '8px'},
            ),
        ]),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Rebut par référence', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Table(style={'width': '100%', 'borderCollapse': 'collapse'}, children=[
                html.Thead(html.Tr([
                    html.Th('Référence',
                            style={'fontSize': '12px', 'color': theme['text_muted'],
                                   'textAlign': 'left', 'padding': '6px 12px',
                                   'fontWeight': '600'}),
                    html.Th('Rebut moyen',
                            style={'fontSize': '12px', 'color': theme['text_muted'],
                                   'textAlign': 'right', 'padding': '6px 12px',
                                   'fontWeight': '600'}),
                ])),
                html.Tbody(rows if rows else [html.Tr(html.Td(
                    'Historique en cours de constitution…', colSpan=2,
                    style={'color': theme['text_muted'], 'padding': '12px',
                           'fontSize': '13px', 'textAlign': 'center'},
                ))]),
            ]),
        ]),
    ])


def build_alerts_side(theme: dict) -> html.Div:
    actives   = store.get_active_alerts(USINE_ID)
    sev_color = {
        'CRITICAL': theme['critical'],
        'WARNING' : theme['warning'],
        'INFO'    : theme.get('accent_cyan', theme['accent_blue']),
    }
    alert_items = []
    if not actives.empty:
        for _, row in actives.head(5).iterrows():
            sev   = row.get('severite', 'INFO')
            color = sev_color.get(sev, theme['text_muted'])
            ts    = row.get('timestamp_debut')
            ts_s  = ts.strftime('%H:%M') if hasattr(ts, 'strftime') else ''
            alert_items.append(html.Div(style={
                'borderRadius': '10px', 'padding': '10px 12px', 'marginBottom': '8px',
                'background': _rgba(color, 0.07),
                'border': f"1px solid {_rgba(color, 0.2)}",
                'borderLeft': f"3px solid {color}",
            }, children=[
                html.Div(style={
                    'display': 'flex', 'justifyContent': 'space-between',
                    'alignItems': 'center', 'marginBottom': '4px',
                }, children=[
                    html.Span(_safe_text(row.get('label', '')),
                              style={'fontSize': '13px', 'fontWeight': '600', 'color': color}),
                    html.Span(ts_s, style={'fontSize': '12px', 'color': theme['text_muted']}),
                ]),
                html.Div(_safe_text(row.get('message_court', '')),
                         style={'fontSize': '13px', 'color': theme['text_secondary'],
                                'lineHeight': '1.4'}),
            ]))
    else:
        alert_items.append(html.Div('Aucune alerte active', style={
            'color': theme['ok'], 'fontSize': '12px', 'padding': '12px',
            'textAlign': 'center', 'fontWeight': '600',
        }))
    return html.Div(className='panel', style={'padding': '16px'}, children=[
        html.Div('Alertes actives', className='panel-title', style={'marginBottom': '12px'}),
        html.Div(alert_items),
    ])


def build_tab_alerts(theme: dict) -> html.Div:
    actives  = store.get_active_alerts(USINE_ID)
    history  = store.get_alert_history(USINE_ID, n_last=30)
    sev_color = {
        'CRITICAL': theme['critical'],
        'WARNING' : theme['warning'],
        'INFO'    : theme.get('accent_cyan', theme['accent_blue']),
    }

    def alert_row(row, is_active=True):
        sev    = row.get('severite', 'INFO')
        color  = sev_color.get(sev, theme['text_muted'])
        ts     = row.get('timestamp_debut')
        ts_s   = ts.strftime('%d %b %H:%M') if hasattr(ts, 'strftime') else ''
        statut = row.get('statut', '')
        return html.Div(style={
            'borderRadius': '12px', 'padding': '14px 16px', 'marginBottom': '8px',
            'background': _rgba(color, 0.06) if is_active else theme['bg_surface'],
            'border': f"1px solid {_rgba(color, 0.18) if is_active else theme['border']}",
            'borderLeft': f"3px solid {color if is_active else theme['border']}",
        }, children=[
            html.Div(style={
                'display': 'flex', 'justifyContent': 'space-between',
                'alignItems': 'flex-start', 'marginBottom': '6px',
            }, children=[
                html.Div(children=[
                    html.Span(_safe_text(row.get('label', sev)),
                              style={'fontSize': '12px', 'fontWeight': '600', 'color': color}),
                    html.Span(f" · {_safe_text(row.get('machine_id',''))}",
                              style={'fontSize': '13px', 'color': theme['text_muted']}),
                ]),
                html.Div(children=[
                    html.Span(ts_s, style={'fontSize': '12px', 'color': theme['text_muted'],
                                           'marginRight': '8px'}),
                    html.Span(_safe_text(statut), style={
                        'fontSize': '12px', 'fontWeight': '600',
                        'color': color if is_active else theme['ok'],
                        'padding': '2px 8px', 'borderRadius': '6px',
                        'border': f"1px solid {_rgba(color if is_active else theme['ok'], 0.3)}",
                        'background': _rgba(color if is_active else theme['ok'], 0.1),
                    }),
                ]),
            ]),
            html.Div(_safe_text(row.get('message_court', '')),
                     style={'fontSize': '13px', 'color': theme['text_secondary'],
                            'marginBottom': '6px', 'lineHeight': '1.4'}),
            html.Div(_safe_text(row.get('recommandation', '')),
                     style={'fontSize': '12px', 'color': theme['text_muted'],
                            'fontStyle': 'italic'}),
        ])

    active_items = (
        [alert_row(row, True) for _, row in actives.iterrows()]
        if not actives.empty else
        [html.Div('Aucune alerte active', style={
            'color': theme['ok'], 'padding': '16px',
            'textAlign': 'center', 'fontSize': '12px', 'fontWeight': '600',
        })]
    )
    hist_items = (
        [alert_row(row, row.get('statut') == 'ACTIVE') for _, row in history.iterrows()]
        if not history.empty else
        [html.Div('Aucun historique d’alerte pour l’instant', style={
            'color': theme['text_muted'], 'padding': '16px',
            'textAlign': 'center', 'fontSize': '12px',
        })]
    )
    return html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                            'gap': '16px'}, children=[
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Alertes actives', className='panel-title', style={'marginBottom': '12px'}),
            html.Div(active_items),
        ]),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Historique des alertes (30 dernières)', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(hist_items, style={'maxHeight': '500px', 'overflowY': 'auto'}),
        ]),
    ])

# ─────────────────────────────────────────────────────────────
# TAB AI — Prédiction RUL Usine A
# ─────────────────────────────────────────────────────────────
_AI_API_URL_A = f'{config.API_BASE_URL}/predict/rul'

_FAULT_PRESETS_A = {
    'usure_critique' : {
        'usure_cumulee_pct': 92.0, 'TRS': 0.71,
        'derive_cycle_pct': 28.0,  'taux_rebut': 0.14,
    },
    'arret_production': {
        'disponibilite': 0.0, 'TRS': 0.0,
        'panne_machine': 1,   'usure_cumulee_pct': 88.0,
    },
}

def build_tab_ai_A(state: dict, theme: dict, active_fault: str | None = None) -> html.Div:
    """Onglet IA : appelle l'API FastAPI et affiche la prédiction RUL."""

    # ── Panneau injection de panne ────────────────────────────
    fault_active = active_fault is not None
    status_color = theme['critical'] if fault_active else theme['ok']
    status_text  = f'Panne injectée : {active_fault}' if fault_active else 'Simulateur en cours'

    def _fault_btn(label, bid, color):
        return html.Button(label, id=bid, n_clicks=0, style={
            'fontSize': '13px', 'fontWeight': '600', 'padding': '6px 16px',
            'borderRadius': '6px', 'border': f'1px solid {_rgba(color, 0.4)}',
            'background': _rgba(color, 0.12), 'color': color, 'cursor': 'pointer',
        })

    fault_panel = html.Div(className='panel', style={'marginBottom': '14px'}, children=[
        html.Div(className='panel-head', children=[
            html.Div(children=[
                html.Div('Injection de panne · Démonstration', className='panel-title'),
                html.Div(status_text, style={
                    'fontSize': '13px', 'fontWeight': '600',
                    'color': status_color, 'marginTop': '2px',
                }),
            ]),
        ]),
        html.Div(style={'padding': '12px 16px', 'display': 'flex', 'gap': '10px',
                        'flexWrap': 'wrap', 'alignItems': 'center'}, children=[
            _fault_btn('Usure critique (92%)', 'fault-btn-usure-A',  theme['warning']),
            _fault_btn('Arrêt production',  'fault-btn-arret-A',  theme['critical']),
            _fault_btn('Reprendre le simulateur','fault-btn-clear-A', theme['ok']),
            html.Div(
                'Le simulateur continue — les champs injectés remplacent ses valeurs jusqu\'à "Reprendre".',
                style={'fontSize': '12px', 'color': theme['text_muted'],
                       'flexBasis': '100%'},
            ),
        ]),
    ])

    # ── Appel API ────────────────────────────────────────────
    api_ok      = False
    rul         = None
    rul_h       = None
    alerte      = 'OK'
    interpreta  = ''
    modele_info = ''
    err_msg     = ''

    payload = {
        'usure_cumulee_pct'   : state.get('usure_cumulee_pct', 50.0),
        'TRS'                 : state.get('TRS', 0.9),
        'temps_cycle_min'     : state.get('temps_cycle_min', 45.0),
        'derive_cycle_pct'    : state.get('derive_cycle_pct', 0.0),
        'disponibilite'       : state.get('disponibilite', 1.0),
        'performance'         : state.get('performance', 1.0),
        'qualite'             : state.get('qualite', 1.0),
        'consommation_kwh'    : state.get('consommation_kwh', 3.1),
        'vitesse_rotation_rpm': state.get('vitesse_rotation_rpm', 1500),
        'couple_nm'           : state.get('couple_nm', 40.0),
        'taux_rebut'          : state.get('taux_rebut', 0.04),
    }

    try:
        resp = requests.post(_AI_API_URL_A, json=payload, timeout=2)
        if resp.status_code == 200:
            data        = resp.json()
            api_ok      = True
            rul         = data.get('rul_sessions', 0)
            rul_h       = data.get('rul_heures', 0)
            alerte      = data.get('niveau_alerte', 'OK')
            interpreta  = data.get('interpretation', '')
            modele_info = data.get('modele', '')
        else:
            err_msg = f"API erreur {resp.status_code}"
    except Exception as e:
        err_msg = f"API indisponible ({config.API_BASE_URL}) — {type(e).__name__}"

    # ── Couleurs alerte ────────────────────────────────────────
    alerte_color = {
        'CRITICAL': theme['critical'],
        'WARNING' : theme['warning'],
        'OK'      : theme['ok'],
    }.get(alerte, theme['text_muted'])

    alerte_bg = _rgba(alerte_color, 0.12)

    # ── Jauge RUL ─────────────────────────────────────────────
    if api_ok:
        max_rul = 80
        rul_val = min(float(rul), max_rul)
        gauge_color = alerte_color
        fig_gauge = go.Figure(go.Indicator(
            mode='gauge+number',
            value=rul_val,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': 'Sessions restantes', 'font': {'size': 13, 'color': theme['text_secondary']}},
            number={'font': {'size': 28, 'color': gauge_color}},
            gauge={
                'axis': {'range': [0, max_rul], 'tickwidth': 1,
                         'tickcolor': theme['text_muted'], 'tickfont': {'size': 10}},
                'bar': {'color': gauge_color, 'thickness': 0.22},
                'bgcolor': theme['bg_surface'], 'borderwidth': 0,
                'steps': [
                    {'range': [0,  10], 'color': _rgba(theme['critical'], 0.14)},
                    {'range': [10, 20], 'color': _rgba(theme['warning'],  0.10)},
                    {'range': [20, max_rul], 'color': _rgba(theme['ok'],  0.06)},
                ],
                'threshold': {'line': {'color': theme['critical'], 'width': 2},
                              'thickness': 0.75, 'value': 10},
            }
        ))
        layout_g = _plot_layout(theme, height=220)
        layout_g['margin'] = dict(l=20, r=20, t=40, b=10)
        fig_gauge.update_layout(layout_g)
        gauge_el = dcc.Graph(figure=fig_gauge, config={'displayModeBar': False})
    else:
        gauge_el = html.Div(
            err_msg,
            style={'fontSize': '12px', 'color': theme['critical'],
                   'padding': '40px 20px', 'textAlign': 'center',
                   'background': _rgba(theme['critical'], 0.06),
                   'borderRadius': '12px', 'fontStyle': 'italic'},
        )

    # ── Carte résultat ─────────────────────────────────────────
    result_card = html.Div(style={
        'display': 'flex', 'flexDirection': 'column', 'gap': '14px',
        'padding': '20px', 'background': theme['bg_surface'],
        'borderRadius': '16px', 'border': f"1px solid {theme['border']}",
    }, children=[
        # Badge alerte
        html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'}, children=[
            html.Span('●', style={'color': alerte_color, 'fontSize': '12px'}),
            html.Span(alerte, style={
                'fontSize': '13px', 'fontWeight': '600', 'color': alerte_color,
                'padding': '3px 10px', 'borderRadius': '6px',
                'background': alerte_bg, 'border': f'1px solid {_rgba(alerte_color, 0.3)}',
            }),
        ]) if api_ok else html.Div(),

        # Valeurs principales
        html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '10px'}, children=[
            html.Div(style={
                'background': theme['bg_card'], 'borderRadius': '12px',
                'padding': '14px', 'border': f"1px solid {theme['border']}",
                'textAlign': 'center',
            }, children=[
                html.Div('Sessions restantes', style={'fontSize': '12px', 'color': theme['text_muted'], 'fontWeight': '600'}),
                html.Div(f'{rul:.0f}' if api_ok else '—',
                         style={'fontSize': '30px', 'fontWeight': '600',
                                'color': alerte_color if api_ok else theme['text_muted']}),
            ]),
            html.Div(style={
                'background': theme['bg_card'], 'borderRadius': '12px',
                'padding': '14px', 'border': f"1px solid {theme['border']}",
                'textAlign': 'center',
            }, children=[
                html.Div('Heures restantes', style={'fontSize': '12px', 'color': theme['text_muted'], 'fontWeight': '600'}),
                html.Div(f'{rul_h:.1f}h' if api_ok else '—',
                         style={'fontSize': '30px', 'fontWeight': '600',
                                'color': alerte_color if api_ok else theme['text_muted']}),
            ]),
        ]) if api_ok else html.Div(),

        # Interprétation
        html.Div(interpreta if api_ok else err_msg, style={
            'fontSize': '12px', 'color': theme['text_secondary'],
            'lineHeight': '1.6', 
        }),
    ])

    # ── Données d'entrée ──────────────────────────────────────
    def kv(label, value, highlight=False):
        return html.Div(style={
            'padding': '8px 12px', 'background': theme['bg_surface'],
            'borderRadius': '8px', 'border': f"1px solid {theme['border']}",
            'borderLeft': f"3px solid {theme['accent_blue']}" if highlight else '',
        }, children=[
            html.Div(label, style={'fontSize': '11px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(f"{payload.get(label.lower().replace(' ', '_'), '—')}", style={
                'fontSize': '13px', 'fontWeight': '600', 'color': theme['text_primary'],
            }),
        ])

    input_row = html.Div(style={
        'display': 'grid', 'gridTemplateColumns': 'repeat(4, 1fr)', 'gap': '8px',
    }, children=[
        html.Div(style={
            'padding': '8px 12px', 'background': theme['bg_surface'],
            'borderRadius': '8px', 'border': f"1px solid {theme['border']}",
            'borderLeft': f"3px solid {theme['accent_blue']}",
        }, children=[
            html.Div('Usure outil', style={'fontSize': '11px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(f"{payload['usure_cumulee_pct']:.1f}%",
                     style={'fontSize': '13px', 'fontWeight': '600', 'color': theme['accent_blue']}),
        ]),
        html.Div(style={
            'padding': '8px 12px', 'background': theme['bg_surface'],
            'borderRadius': '8px', 'border': f"1px solid {theme['border']}",
        }, children=[
            html.Div('TRS', style={'fontSize': '11px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(f"{payload['TRS']*100:.1f}%",
                     style={'fontSize': '13px', 'fontWeight': '600', 'color': theme['text_primary']}),
        ]),
        html.Div(style={
            'padding': '8px 12px', 'background': theme['bg_surface'],
            'borderRadius': '8px', 'border': f"1px solid {theme['border']}",
        }, children=[
            html.Div('Cycle', style={'fontSize': '11px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(f"{payload['temps_cycle_min']:.1f} min",
                     style={'fontSize': '13px', 'fontWeight': '600', 'color': theme['text_primary']}),
        ]),
        html.Div(style={
            'padding': '8px 12px', 'background': theme['bg_surface'],
            'borderRadius': '8px', 'border': f"1px solid {theme['border']}",
        }, children=[
            html.Div('Dérive cycle', style={'fontSize': '11px', 'color': theme['text_muted'], 'fontWeight': '600'}),
            html.Div(f"{payload['derive_cycle_pct']:.1f}%",
                     style={'fontSize': '13px', 'fontWeight': '600', 'color': theme['text_primary']}),
        ]),
    ])

    source_badge = html.Div(
        'Panne injectée' if fault_active else 'Simulateur',
        style={
            'fontSize': '12px', 'fontWeight': '600', 'padding': '3px 10px',
            'borderRadius': '6px',
            'color': theme['critical'] if fault_active else theme['text_muted'],
            'background': _rgba(theme['critical'] if fault_active else theme['text_muted'], 0.10),
            'border': f"1px solid {_rgba(theme['critical'] if fault_active else theme['text_muted'], 0.25)}",
        },
    )

    return html.Div(children=[
        fault_panel,
        html.Div(className='panel', style={'marginBottom': '14px'}, children=[
            html.Div(className='panel-head', children=[
                html.Div(children=[
                    html.Div('Maintenance prédictive — durée de vie de l’outil', className='panel-title'),
                    html.Div(
                        f'Durée de vie restante de l’outil · {modele_info}' if api_ok
                        else 'Durée de vie restante de l’outil · modèle indisponible',
                        className='panel-subtitle',
                    ),
                ]),
                html.Div(style={'display': 'flex', 'gap': '8px', 'alignItems': 'center'}, children=[
                    source_badge,
                    html.Div('MSPR 841', style={
                        'fontSize': '12px', 'fontWeight': '600', 'padding': '3px 10px',
                        'borderRadius': '6px', 'color': theme['accent_purple'],
                        'background': _rgba(theme['accent_purple'], 0.10),
                        'border': f"1px solid {_rgba(theme['accent_purple'], 0.25)}",
                    }),
                ]),
            ]),
            html.Div(style={
                'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                'gap': '16px', 'padding': '16px',
            }, children=[
                gauge_el,
                result_card,
            ]),
        ]),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Données d\'entrée · Session courante', className='panel-title',
                     style={'marginBottom': '12px'}),
            input_row,
            html.Div(
                '⚠ Modèle entraîné sur données simulées : erreur moyenne d\'environ une session '
                '(30 min). Recalibrage sur données terrain nécessaire avant mise en production.',
                style={'fontSize': '12px', 'color': theme['text_muted'],
                       'marginTop': '10px', 'fontStyle': 'italic'},
            ),
        ]),
    ])


# ─────────────────────────────────────────────────────────────
# LAYOUT — dcc.Store et tab-bar-container HORS du contenu
# ─────────────────────────────────────────────────────────────
app.layout = shell.racine([
    dcc.Interval(id='interval-A', interval=1000, n_intervals=0),
    dcc.Store(id='tab-store-A', data='overview'),
    dcc.Store(id='fault-store-A', data=None),   # panne injectée, ou None
    html.Div(id='nav-A', className='nav-zone'),
    html.Div(id='haut-A'),
    # barre d'onglets dans son propre conteneur : elle n'est pas recréée à chaque tick
    html.Div(id='tab-bar-container-A', className='onglets-zone'),
    html.Main(id='page-content-A', className='page-wrap'),
], id_racine='root-A')

# ─────────────────────────────────────────────────────────────
# CALLBACK 1 — Switch onglet (déclenché par clics uniquement)
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('tab-store-A', 'data'),
    Input('tab-btn-overview-A',    'n_clicks'),
    Input('tab-btn-maintenance-A', 'n_clicks'),
    Input('tab-btn-quality-A',     'n_clicks'),
    Input('tab-btn-alerts-A',      'n_clicks'),
    Input('tab-btn-ai-A',          'n_clicks'),
    prevent_initial_call=True,
)
def switch_tab_A(n1, n2, n3, n4, n5):
    mapping = {
        'tab-btn-overview-A'    : 'overview',
        'tab-btn-maintenance-A' : 'maintenance',
        'tab-btn-quality-A'     : 'quality',
        'tab-btn-alerts-A'      : 'alerts',
        'tab-btn-ai-A'          : 'ai',
    }
    return mapping.get(ctx.triggered_id, 'overview')

# ─────────────────────────────────────────────────────────────
# CALLBACK 2 — Tab bar (rendue une seule fois au changement
#              d'onglet, jamais au tick interval)
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('tab-bar-container-A', 'children'),
    Input('tab-store-A', 'data'),
)
def update_tab_bar_A(active_tab):
    return shell.barre_onglets([
        ('Vue d’ensemble', 'overview', 'tab-btn-overview-A'),
        ('Maintenance', 'maintenance', 'tab-btn-maintenance-A'),
        ('Qualité', 'quality', 'tab-btn-quality-A'),
        ('Alertes', 'alerts', 'tab-btn-alerts-A'),
        ('Prédictions IA', 'ai', 'tab-btn-ai-A'),
    ], active_tab)

# ─────────────────────────────────────────────────────────────
# CALLBACK 3 — Contenu principal (interval uniquement,
#              tab-store en State → ne déclenche pas de reset)
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('nav-A', 'children'),
    Output('haut-A', 'children'),
    Output('page-content-A', 'children'),
    Input('interval-A', 'n_intervals'),
    State('tab-store-A', 'data'),        # ← State, pas Input
    State('fault-store-A', 'data'),
)
def update_page_A(n, active_tab, active_fault):
    ensure_simulator_started()
    theme      = _soft_theme(DEFAULT_THEME_MODE)
    state      = store.get_current_state(USINE_ID)
    aggs       = store.get_aggregations(USINE_ID)
    all_alts   = store.get_active_alerts(USINE_ID)
    persistent = _get_persistent_alerts(all_alts)

    ts_str = '—'
    sim    = store.get_sim_state(USINE_ID)
    ts     = sim.get('timestamp_simule')
    if ts and hasattr(ts, 'strftime'):
        ts_str = ts.strftime('%d/%m/%Y · %H:%M')

    if active_tab == 'maintenance':
        tab_content = build_tab_maintenance(state, theme)
    elif active_tab == 'quality':
        tab_content = build_tab_quality(state, theme)
    elif active_tab == 'alerts':
        tab_content = build_tab_alerts(theme)
    elif active_tab == 'ai':
        tab_content = build_tab_ai_A(state, theme, active_fault)
    else:
        tab_content = build_tab_overview(state, aggs, theme)

    haut = html.Div(className='page-wrap haut', children=[
        shell.entete(
            _safe_text(SITE_LABEL),
            f'Point de vigilance du site : {_safe_text(DOMINANT).lower()}',
            ts_str,
            state.get('statut_global', 'INIT'),
        ),
        build_alert_banner(persistent, theme),
        build_kpi_strip(state, aggs, theme),
    ])
    contenu = [
        tab_content,
        shell.pied(f'MECHA · Supervision de production · {_safe_text(SITE_LABEL)} · données simulées'),
    ]
    return shell.navigation(USINE_ID), haut, contenu

# ─────────────────────────────────────────────────────────────
# CALLBACK INJECTION DE PANNE — Usine A
# Modifie directement le store (thread-safe).
# Le simulateur continue ; get_current_state() applique les overrides.
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('fault-store-A', 'data'),
    Input('fault-btn-usure-A', 'n_clicks'),
    Input('fault-btn-arret-A', 'n_clicks'),
    Input('fault-btn-clear-A', 'n_clicks'),
    prevent_initial_call=True,
)
def handle_fault_A(n_usure, n_arret, n_clear):
    triggered = bouton_clique(ctx.triggered)
    if triggered is None:      # simple rafraîchissement de l'onglet, aucun clic
        raise PreventUpdate
    if triggered == 'fault-btn-usure-A':
        store.inject_fault(USINE_ID, _FAULT_PRESETS_A['usure_critique'])
        return 'Usure critique (92%)'
    if triggered == 'fault-btn-arret-A':
        store.inject_fault(USINE_ID, _FAULT_PRESETS_A['arret_production'])
        return 'Arrêt production'
    # fault-btn-clear-A
    store.clear_fault(USINE_ID)
    return None


# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    ensure_simulator_started()
    app.run(debug=False, port=PORT, host='0.0.0.0')