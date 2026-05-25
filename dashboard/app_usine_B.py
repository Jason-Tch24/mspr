# ============================================================
# app_usine_B.py — MECHA Site Dashboard · Usine B · Port 8052
#
# Problème dominant : Pannes thermiques clustérisées
# Fix : tab-store en State dans update_page_B
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

import store
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
USINE_ID   = 'Usine_B'
PORT       = 8052
SITE_LABEL = USINE_LABELS[USINE_ID]
DOMINANT   = USINE_DOMINANT_PROBLEM[USINE_ID]

DEFAULT_THEME_MODE = 'dark'

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
_ALERT_TTL    = {'CRITICAL': 999999, 'WARNING': 10, 'INFO': 6}

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _safe_text(value) -> str:
    if not value: return ""
    txt = str(value).replace("_", " ").replace("—", "·").strip()
    while "  " in txt: txt = txt.replace("  ", " ")
    return txt

def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f}%"

def _fmt_trs_color(trs: float, theme: dict) -> str:
    if trs >= 0.90: return theme['ok']
    if trs >= 0.80: return theme['warning']
    return theme['critical']

def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    if len(h) != 6: return f'rgba(255,255,255,{alpha})'
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

def _soft_theme(mode: str) -> dict:
    base = get_theme(mode or 'dark')
    if mode == 'light':
        premium = {
            'bg_primary': '#f4f6f8', 'bg_secondary': '#e9edf2',
            'bg_card': 'rgba(255,255,255,0.96)', 'bg_surface': '#f8fafc',
            'bg_sidebar': 'rgba(255,255,255,0.94)',
            'text_primary': '#101828', 'text_secondary': '#475467',
            'text_muted': '#667085', 'border': 'rgba(16,24,40,0.08)',
            'accent_blue': '#315ea8', 'accent_purple': '#4f5f9f',
            'accent_cyan': '#3f7f8f', 'accent_green': '#2e8b57',
            'accent_orange': '#b7791f', 'ok': '#2f855a',
            'warning': '#b7791f', 'critical': '#b54747',
            'chart_fill': 'rgba(49,94,168,0.10)',
            'glass': 'rgba(255,255,255,0.72)',
        }
    else:
        premium = {
            'bg_primary': '#071018', 'bg_secondary': '#0b1620',
            'bg_card': 'rgba(15,24,34,0.97)', 'bg_surface': '#111c28',
            'bg_sidebar': 'rgba(10,18,27,0.98)',
            'text_primary': '#ecf2f8', 'text_secondary': '#b0bcc9',
            'text_muted': '#7d8a98', 'border': 'rgba(255,255,255,0.07)',
            'accent_blue': '#5b7fa3', 'accent_purple': '#6b7394',
            'accent_cyan': '#5b8f95', 'accent_green': '#4d8c6f',
            'accent_orange': '#b68a52', 'ok': '#4d8c6f',
            'warning': '#b68a52', 'critical': '#b85c5c',
            'chart_fill': 'rgba(91,127,163,0.10)',
            'glass': 'rgba(255,255,255,0.025)',
        }
    return {**base, **premium}

def _theme_vars(theme: dict) -> dict:
    return {
        '--bg-primary'   : theme['bg_primary'],
        '--bg-secondary' : theme.get('bg_secondary', theme['bg_primary']),
        '--bg-card'      : theme['bg_card'],
        '--bg-surface'   : theme['bg_surface'],
        '--bg-sidebar'   : theme.get('bg_sidebar', theme['bg_card']),
        '--text-primary' : theme['text_primary'],
        '--text-secondary': theme['text_secondary'],
        '--text-muted'   : theme['text_muted'],
        '--border'       : theme['border'],
        '--accent-blue'  : theme['accent_blue'],
        '--accent-purple': theme['accent_purple'],
        '--accent-cyan'  : theme.get('accent_cyan', theme['accent_blue']),
        '--accent-green' : theme.get('accent_green', theme['ok']),
        '--accent-orange': theme.get('accent_orange', theme['warning']),
        '--ok'           : theme['ok'],
        '--warning'      : theme['warning'],
        '--critical'     : theme['critical'],
        '--chart-fill'   : theme['chart_fill'],
        '--glass'        : theme.get('glass', 'rgba(255,255,255,0.04)'),
    }

def _statut_config(statut: str, theme: dict) -> dict:
    mapping = {
        'CRITICAL': {'color': theme['critical'], 'bg': _rgba(theme['critical'], 0.12),
                     'border': _rgba(theme['critical'], 0.28), 'label': 'Critical',
                     'dot': theme['critical']},
        'WARNING':  {'color': theme['warning'],  'bg': _rgba(theme['warning'],  0.12),
                     'border': _rgba(theme['warning'],  0.28), 'label': 'Attention',
                     'dot': theme['warning']},
        'OK':       {'color': theme['ok'],        'bg': _rgba(theme['ok'],       0.12),
                     'border': _rgba(theme['ok'],       0.22), 'label': 'Normal',
                     'dot': theme['ok']},
        'INIT':     {'color': theme['text_muted'],'bg': _rgba('#94a3b8', 0.10),
                     'border': theme['border'],                'label': 'Init',
                     'dot': theme['text_muted']},
    }
    return mapping.get(statut, {
        'color': theme['text_muted'], 'bg': _rgba('#94a3b8', 0.08),
        'border': theme['border'], 'label': statut, 'dot': theme['text_muted'],
    })

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
        font=dict(family='Inter, sans-serif', color=theme['text_muted'], size=10),
        margin=dict(l=40, r=16, t=36, b=32),
        height=height,
        title=dict(text=title,
                   font=dict(size=11, color=theme['text_secondary']),
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
        tickfont=dict(size=9, color=theme['text_muted']),
        title=dict(text=title, font=dict(size=9, color=theme['text_muted'])),
        showgrid=True, zeroline=False,
    )

# ─────────────────────────────────────────────────────────────
# COMPOSANTS SHELL
# ─────────────────────────────────────────────────────────────

def build_sidebar(theme: dict) -> html.Div:
    return html.Div(className='sidebar', children=[
        html.Div(className='sidebar-top', children=[
            html.Div(className='brand-lockup', children=[
                html.Div(className='brand-logo', children=[
                    html.Div(className='brand-logo-stem brand-logo-stem-left'),
                    html.Div(className='brand-logo-stem brand-logo-stem-mid'),
                    html.Div(className='brand-logo-stem brand-logo-stem-right'),
                ]),
                html.Div('MECHA', className='brand-text'),
            ]),
            html.Div(className='nav-stack', children=[
                html.A(
                    html.Div(className='nav-pill',
                             children=[html.Div(className='nav-icon')]),
                    href='http://localhost:8050', title='Group Dashboard'
                ),
                html.Div(className='nav-pill active',
                         children=[html.Div(className='nav-icon')],
                         title=SITE_LABEL),
            ]),
        ]),
        html.Div(className='sidebar-top', children=[
            html.Div(className='nav-pill', children=[html.Div(className='nav-icon')]),
        ]),
    ])


def build_topbar(theme: dict, ts_str: str) -> html.Div:
    state    = store.get_current_state(USINE_ID)
    statut   = state.get('statut_global', 'INIT')
    sc       = _statut_config(statut, theme)
    nb_alert = state.get('nb_alertes_actives', 0)
    return html.Div(className='topbar', children=[
        html.Div(className='topbar-left', children=[
            html.Div(className='search-shell', children=[
                html.Div(className='search-dot'),
                html.Span(_safe_text(SITE_LABEL), className='search-text'),
            ]),
        ]),
        html.Div(className='topbar-right', children=[
            html.Div(children=[
                html.Span('● ', style={'color': sc['dot'], 'fontSize': '8px'}),
                html.Span(sc['label'],
                          style={'fontSize': '11px', 'color': sc['color'], 'fontWeight': '600'}),
            ], style={
                'display': 'flex', 'alignItems': 'center', 'gap': '4px',
                'padding': '4px 10px', 'borderRadius': '999px',
                'border': f"1px solid {sc['border']}", 'background': sc['bg'],
            }),
            html.Div(
                f"{'⚠ ' if nb_alert > 0 else ''}{nb_alert} alert{'s' if nb_alert != 1 else ''}",
                style={
                    'fontSize': '11px', 'fontWeight': '600',
                    'padding': '4px 10px', 'borderRadius': '999px',
                    'border': f"1px solid {theme['border']}",
                    'color': theme['critical'] if nb_alert > 0 else theme['text_muted'],
                    'background': theme.get('glass', 'rgba(255,255,255,0.03)'),
                }
            ),
            html.Div(className='profile-chip', children=[
                html.Div('B', className='avatar'),
                html.Div(className='profile-meta', children=[
                    html.Div('Site Manager', className='profile-name'),
                    html.Div(_safe_text(USINE_ID), className='profile-role'),
                ]),
            ]),
        ]),
    ])


def build_hero(theme: dict, ts_str: str) -> html.Div:
    state  = store.get_current_state(USINE_ID)
    trs    = state.get('TRS', 0.0)
    statut = state.get('statut_global', 'INIT')
    sc     = _statut_config(statut, theme)
    return html.Div(className='page-hero', children=[
        html.Div(children=[
            html.Div('INDUSTRIAL SITE', className='eyebrow'),
            html.H1(_safe_text(SITE_LABEL), className='hero-title'),
            html.Div(_safe_text(DOMINANT),  className='hero-subtitle'),
            html.Div(className='meta-row', children=[
                html.Div(className='meta-badge', children=[
                    html.Div(className='live-dot'),
                    html.Span('Live monitoring'),
                ]),
                html.Div(className='meta-badge',
                         children=[html.Span(f'Simulated time · {ts_str}')]),
                html.Div(className='meta-badge', children=[
                    html.Span(f'TRS · {_fmt_pct(trs)}',
                              style={'color': _fmt_trs_color(trs, theme)}),
                ]),
            ]),
        ]),
        html.Div(className='hero-actions', children=[
            html.Div(children=[
                html.Span('● ', style={'color': sc['dot'], 'fontSize': '10px'}),
                html.Span(sc['label'], style={'fontWeight': '700'}),
            ], style={
                'display': 'flex', 'alignItems': 'center', 'gap': '6px',
                'padding': '8px 16px', 'borderRadius': '12px',
                'border': f"1px solid {sc['border']}", 'background': sc['bg'],
                'color': sc['color'], 'fontSize': '12px', 'fontWeight': '700',
            }),
        ]),
    ])


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
    icon  = {'CRITICAL': '✕', 'WARNING': '⚠', 'INFO': 'ℹ'}.get(sev, '·')
    extra = f"  +{len(persistent_alerts)-1} more" if len(persistent_alerts) > 1 else ""
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
                      style={'color': theme['text_muted'], 'fontSize': '11px',
                             'marginLeft': '8px'}),
        ]),
    ])

# ─────────────────────────────────────────────────────────────
# KPI STRIP — Usine B : Delta thermique à la place de l'usure
# ─────────────────────────────────────────────────────────────

def build_kpi_strip(state: dict, aggs: dict, theme: dict) -> html.Div:
    trs      = state.get('TRS', 0.0)
    rebut    = state.get('taux_rebut', 0.0)
    delta_t  = state.get('temp_process_delta', 0.0)
    energie  = state.get('consommation_kwh', 0.0)
    agg_1h   = aggs.get('1h', {})
    trs_1h   = agg_1h.get('TRS_moyen', 0.0)
    rebut_1h = agg_1h.get('rebut_moyen', 0.0)
    nb_pan   = agg_1h.get('nb_pannes', 0)

    delta_color = (theme['critical'] if delta_t < 7.0 else
                   theme['warning']  if delta_t < 8.6 else theme['ok'])

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

    return html.Div(style={
        'display': 'grid', 'gridTemplateColumns': 'repeat(4,1fr)',
        'gap': '12px', 'marginBottom': '16px',
    }, children=[
        card('TRS Current', _fmt_pct(trs),
             f'1h avg · {_fmt_pct(trs_1h)}',
             _fmt_trs_color(trs, theme), trs * 100),
        card('Scrap Rate', _fmt_pct(rebut),
             f'1h avg · {_fmt_pct(rebut_1h)}',
             theme['critical'] if rebut > 0.08 else
             theme['warning']  if rebut > 0.05 else theme['ok']),
        card('Thermal Delta', f'{delta_t:.2f} K',
             f'HDF threshold · 8.6 K  ·  {nb_pan} failure(s)/1h',
             delta_color),
        card('Energy / session', f'{energie:.2f} kWh',
             'Current session', theme['accent_blue']),
    ])

# ─────────────────────────────────────────────────────────────
# MACHINE GRID
# ─────────────────────────────────────────────────────────────

def build_machine_grid(theme: dict) -> html.Div:
    machines = store.get_machine_states(USINE_ID)
    statut_labels = {
        'EN_PRODUCTION': ('Running',     theme['ok']),
        'ARRET':         ('Stopped',     theme['critical']),
        'MAINTENANCE':   ('Maintenance', theme['warning']),
        'STANDBY':       ('Standby',     theme['text_muted']),
        'INIT':          ('Init',        theme['text_muted']),
    }
    cards = []
    for m_id, m_state in machines.items():
        statut       = m_state.get('statut', 'INIT')
        label, color = statut_labels.get(statut, (statut, theme['text_muted']))
        usure        = m_state.get('usure_pct', 0.0)
        rebut        = m_state.get('taux_rebut', 0.0)
        u_color      = (theme['critical'] if usure > 90 else
                        theme['warning']  if usure > 75 else theme['ok'])
        cards.append(html.Div(style={
            'borderRadius': '14px', 'border': f"1px solid {theme['border']}",
            'background': theme['bg_surface'], 'padding': '14px',
        }, children=[
            html.Div(style={
                'display': 'flex', 'justifyContent': 'space-between',
                'alignItems': 'center', 'marginBottom': '10px',
            }, children=[
                html.Span(m_id, style={'fontWeight': '700', 'fontSize': '13px',
                                       'color': theme['text_primary']}),
                html.Span(label, style={
                    'fontSize': '10px', 'fontWeight': '700', 'color': color,
                    'padding': '2px 8px', 'borderRadius': '999px',
                    'border': f'1px solid {_rgba(color, 0.3)}',
                    'background': _rgba(color, 0.1),
                }),
            ]),
            html.Div(className='bar-row', children=[
                html.Span('W', className='bar-label'),
                html.Div(className='bar-track', children=[
                    html.Div(className='bar-fill',
                             style={'width': f'{min(usure,100):.0f}%',
                                    'background': u_color})
                ]),
                html.Span(f'{usure:.0f}%', className='bar-value'),
            ]),
            html.Div(f'Scrap · {rebut*100:.1f}%',
                     style={'marginTop': '6px', 'fontSize': '10px',
                            'color': theme['text_muted']}),
        ]))
    return html.Div(children=[
        html.Div('Machine Status', style={
            'fontSize': '11px', 'fontWeight': '700',
            'color': theme['text_muted'], 'textTransform': 'uppercase',
            'letterSpacing': '0.1em', 'marginBottom': '10px',
        }),
        html.Div(style={
            'display': 'grid', 'gridTemplateColumns': 'repeat(2,1fr)', 'gap': '10px',
        }, children=cards),
    ])

# ─────────────────────────────────────────────────────────────
# GRAPHIQUES USINE B
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
        lcl = lim.get('TRS', {}).get('lcl', 0.86)
    except Exception:
        lcl = 0.86

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
                x=ts, y=ma, mode='lines', name='Moving avg',
                line=dict(color=theme.get('accent_green', theme['ok']), width=2),
                hovertemplate='MA : %{y:.3f}<extra></extra>',
            ))
    fig.add_hline(y=lcl, line_dash='dot', line_color=theme['critical'], line_width=1,
                  annotation_text=f'LCL {lcl:.2f}',
                  annotation_font_size=9, annotation_font_color=theme['critical'],
                  annotation_position='bottom right')
    fig.add_hline(y=TRS_SEUIL_ACCEPTABLE, line_dash='dot',
                  line_color=theme['warning'], line_width=1,
                  annotation_text='Target 85%',
                  annotation_font_size=9, annotation_font_color=theme['warning'],
                  annotation_position='top right')
    layout = _plot_layout(theme, 'TRS — Real-time trend', height=260)
    layout['xaxis']      = _axis(theme)
    layout['yaxis']      = {**_axis(theme, 'TRS'), 'range': [0.60, 1.05]}
    layout['showlegend'] = True
    layout['legend']     = dict(font=dict(size=9, color=theme['text_muted']),
                                bgcolor='rgba(0,0,0,0)', orientation='h', x=0, y=1.12)
    fig.update_layout(layout)
    return dcc.Graph(figure=fig, config={'displayModeBar': False})


def build_thermal_chart(theme: dict) -> dcc.Graph:
    """Signal thermique et pannes HDF — signature Usine B."""
    import json
    from config import LIMITS_PATHS
    trend = kpi_engine.get_thermal_trend(USINE_ID, n_sessions=96)
    ts    = trend.get('timestamps', [])
    delta = trend.get('delta_values', [])
    hdf   = trend.get('hdf_flags', [])
    try:
        with open(LIMITS_PATHS[USINE_ID]) as f:
            lim = json.load(f)
        lcl_delta = lim.get('temp_process_delta', {}).get('lcl', 5.93)
    except Exception:
        lcl_delta = 5.93

    fig = go.Figure()
    if delta:
        fig.add_trace(go.Scatter(
            x=ts, y=delta, mode='lines', name='Thermal delta',
            line=dict(color=theme['accent_cyan'], width=1.4),
            fill='tozeroy', fillcolor=_rgba(theme['accent_cyan'], 0.07),
            hovertemplate='Delta T : %{y:.2f} K<extra></extra>',
        ))
    if hdf and ts and delta:
        hdf_ts  = [t for t, h in zip(ts, hdf) if h == 1]
        hdf_val = [d for d, h in zip(delta, hdf) if h == 1]
        if hdf_ts:
            fig.add_trace(go.Scatter(
                x=hdf_ts, y=hdf_val, mode='markers', name='HDF failure',
                marker=dict(color=theme['critical'], size=7, symbol='x',
                            line=dict(width=2, color=theme['critical'])),
                hovertemplate='HDF failure<br>Delta T : %{y:.2f} K<extra></extra>',
            ))
    fig.add_hline(y=lcl_delta, line_dash='dot', line_color=theme['critical'],
                  line_width=1.2,
                  annotation_text=f'Critical threshold {lcl_delta:.1f} K',
                  annotation_font_size=9, annotation_font_color=theme['critical'],
                  annotation_position='top right')
    layout = _plot_layout(theme, 'Thermal Delta — HDF precursor signal', height=300)
    layout['xaxis']      = _axis(theme)
    layout['yaxis']      = {**_axis(theme, 'Delta T (K)'), 'range': [0, 20]}
    layout['showlegend'] = True
    layout['legend']     = dict(font=dict(size=9, color=theme['text_muted']),
                                bgcolor='rgba(0,0,0,0)', orientation='h', x=0, y=1.1)
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
                        html.Div('TRS Monitoring', className='panel-title'),
                        html.Div('Real-time OEE with SPC control limits',
                                 className='panel-subtitle'),
                    ]),
                ]),
                html.Div(style={'padding': '0 16px 16px 16px'},
                         children=[build_trs_chart(theme)]),
            ]),
            html.Div(className='panel', children=[
                html.Div(className='panel-head', children=[
                    html.Div(children=[
                        html.Div('Thermal Signal & HDF Clusters', className='panel-title'),
                        html.Div('Thermal delta vs critical threshold — Usine B dominant pattern',
                                 className='panel-subtitle'),
                    ]),
                ]),
                html.Div(style={'padding': '0 16px 16px 16px'},
                         children=[build_thermal_chart(theme)]),
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
    nb_hdf       = int(state.get('panne_thermique', 0))

    def gauge_usure(m_id, usure_pct):
        color = (theme['critical'] if usure_pct > 90 else
                 theme['warning']  if usure_pct > 75 else theme['ok'])
        fig = go.Figure(go.Indicator(
            mode='gauge+number', value=usure_pct,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': m_id,
                   'font': {'size': 11, 'color': theme['text_secondary']}},
            number={'suffix': '%', 'font': {'size': 20, 'color': color}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1,
                         'tickcolor': theme['text_muted'],
                         'tickfont': {'size': 8}},
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
        u     = m_state.get('usure_pct', 0.0)
        est_h = round((100 - u) / max(u, 1) * 2, 1) if u > 0 else 0
        c_est = (theme['critical'] if u > 90 else
                 theme['warning']  if u > 75 else theme['ok'])
        gauges.append(html.Div(style={
            'borderRadius': '16px', 'border': f"1px solid {theme['border']}",
            'background': theme['bg_surface'], 'padding': '12px', 'textAlign': 'center',
        }, children=[
            dcc.Graph(figure=gauge_usure(m_id, u), config={'displayModeBar': False}),
            html.Div(f'Est. replacement in ~{est_h}h',
                     style={'fontSize': '10px', 'color': c_est,
                            'fontWeight': '600', 'marginTop': '4px'}),
        ]))

    def stat_card(title, value, color):
        return html.Div(style={
            'borderRadius': '12px', 'border': f"1px solid {theme['border']}",
            'padding': '14px', 'background': theme['bg_surface'],
        }, children=[
            html.Div(title, style={'fontSize': '10px', 'color': theme['text_muted'],
                                   'textTransform': 'uppercase', 'fontWeight': '700'}),
            html.Div(str(value), style={'fontSize': '22px', 'fontWeight': '700',
                                        'color': color, 'marginTop': '6px'}),
        ])

    return html.Div(children=[
        html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(4,1fr)',
                        'gap': '12px', 'marginBottom': '16px'}, children=gauges),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Maintenance Summary', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(4,1fr)',
                            'gap': '10px'}, children=[
                stat_card('Active machine',          _safe_text(machine_id), theme['text_primary']),
                stat_card('Tool replacements today', remplacement,           theme['accent_blue']),
                stat_card('Failures last 7 days',    nb_pannes_7j,
                          theme['warning'] if nb_pannes_7j > 3 else theme['ok']),
                stat_card('HDF this session',        nb_hdf,
                          theme['critical'] if nb_hdf > 0 else theme['ok']),
            ]),
        ]),
    ])


def build_tab_quality(state: dict, theme: dict) -> html.Div:
    buf          = store.get_buffer_as_df(USINE_ID)
    taux_rebut   = state.get('taux_rebut', 0.0)
    pieces_rebut = state.get('pieces_rebutees', 0)
    type_piece   = state.get('type_piece', 'N/A')
    equipe       = state.get('equipe', 'N/A')
    delta_t      = state.get('temp_process_delta', 0.0)
    rebut_color  = (theme['critical'] if taux_rebut > 0.08 else
                    theme['warning']  if taux_rebut > 0.05 else theme['ok'])
    delta_color  = (theme['critical'] if delta_t < 7.0 else
                    theme['warning']  if delta_t < 8.6 else theme['ok'])

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
                               'color': color, 'fontWeight': '700',
                               'textAlign': 'right'}),
            ], style={'borderBottom': f"1px solid {theme['border']}"}))

    def summary_card(title, value, color):
        return html.Div(style={
            'borderRadius': '12px', 'border': f"1px solid {theme['border']}",
            'padding': '12px', 'background': theme['bg_surface'],
        }, children=[
            html.Div(title, style={'fontSize': '10px', 'color': theme['text_muted'],
                                   'textTransform': 'uppercase', 'fontWeight': '700'}),
            html.Div(value, style={'fontSize': '26px', 'fontWeight': '700',
                                   'color': color, 'marginTop': '6px'}),
        ])

    return html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                            'gap': '16px'}, children=[
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Quality & Thermal Summary', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(2,1fr)',
                            'gap': '10px', 'marginBottom': '12px'}, children=[
                summary_card('Scrap rate',    f"{taux_rebut*100:.2f}%", rebut_color),
                summary_card('Parts scrapped', str(pieces_rebut),       theme['text_primary']),
                summary_card('Thermal delta',  f'{delta_t:.2f} K',     delta_color),
                summary_card('HDF threshold',  '8.6 K',                theme['text_muted']),
            ]),
            html.Div(
                f'Active reference : {_safe_text(type_piece)}  ·  Team : {_safe_text(equipe)}',
                style={'fontSize': '11px', 'color': theme['text_muted'], 'marginTop': '8px'},
            ),
        ]),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Scrap by Reference', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Table(style={'width': '100%', 'borderCollapse': 'collapse'}, children=[
                html.Thead(html.Tr([
                    html.Th('Reference',
                            style={'fontSize': '10px', 'color': theme['text_muted'],
                                   'textAlign': 'left', 'padding': '6px 12px',
                                   'fontWeight': '700', 'textTransform': 'uppercase'}),
                    html.Th('Avg Scrap',
                            style={'fontSize': '10px', 'color': theme['text_muted'],
                                   'textAlign': 'right', 'padding': '6px 12px',
                                   'fontWeight': '700', 'textTransform': 'uppercase'}),
                ])),
                html.Tbody(rows if rows else [html.Tr(html.Td(
                    'Building history...', colSpan=2,
                    style={'color': theme['text_muted'], 'padding': '12px',
                           'fontSize': '11px', 'textAlign': 'center'},
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
                              style={'fontSize': '11px', 'fontWeight': '700',
                                     'color': color}),
                    html.Span(ts_s, style={'fontSize': '10px',
                                           'color': theme['text_muted']}),
                ]),
                html.Div(_safe_text(row.get('message_court', '')),
                         style={'fontSize': '11px', 'color': theme['text_secondary'],
                                'lineHeight': '1.4'}),
            ]))
    else:
        alert_items.append(html.Div('No active alerts', style={
            'color': theme['ok'], 'fontSize': '12px', 'padding': '12px',
            'textAlign': 'center', 'fontWeight': '600',
        }))
    return html.Div(className='panel', style={'padding': '16px'}, children=[
        html.Div('Active Alerts', className='panel-title', style={'marginBottom': '12px'}),
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
                              style={'fontSize': '12px', 'fontWeight': '700',
                                     'color': color}),
                    html.Span(f" · {_safe_text(row.get('machine_id',''))}",
                              style={'fontSize': '11px', 'color': theme['text_muted']}),
                ]),
                html.Div(children=[
                    html.Span(ts_s, style={'fontSize': '10px',
                                           'color': theme['text_muted'],
                                           'marginRight': '8px'}),
                    html.Span(_safe_text(statut), style={
                        'fontSize': '10px', 'fontWeight': '700',
                        'color': color if is_active else theme['ok'],
                        'padding': '2px 8px', 'borderRadius': '999px',
                        'border': f"1px solid {_rgba(color if is_active else theme['ok'], 0.3)}",
                        'background': _rgba(color if is_active else theme['ok'], 0.1),
                    }),
                ]),
            ]),
            html.Div(_safe_text(row.get('message_court', '')),
                     style={'fontSize': '11px', 'color': theme['text_secondary'],
                            'marginBottom': '6px', 'lineHeight': '1.4'}),
            html.Div(_safe_text(row.get('recommandation', '')),
                     style={'fontSize': '10px', 'color': theme['text_muted'],
                            'fontStyle': 'italic'}),
        ])

    active_items = (
        [alert_row(row, True) for _, row in actives.iterrows()]
        if not actives.empty else
        [html.Div('No active alerts', style={
            'color': theme['ok'], 'padding': '16px',
            'textAlign': 'center', 'fontSize': '12px', 'fontWeight': '600',
        })]
    )
    hist_items = (
        [alert_row(row, row.get('statut') == 'ACTIVE') for _, row in history.iterrows()]
        if not history.empty else
        [html.Div('No alert history yet', style={
            'color': theme['text_muted'], 'padding': '16px',
            'textAlign': 'center', 'fontSize': '12px',
        })]
    )
    return html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                            'gap': '16px'}, children=[
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Active Alerts', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(active_items),
        ]),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Alert History (last 30)', className='panel-title',
                     style={'marginBottom': '12px'}),
            html.Div(hist_items, style={'maxHeight': '500px', 'overflowY': 'auto'}),
        ]),
    ])

# ─────────────────────────────────────────────────────────────
# TAB AI — Classification risque thermique Usine B
# ─────────────────────────────────────────────────────────────
_AI_API_URL_B = 'http://localhost:8000/predict/risque-thermique'

def build_tab_ai_B(state: dict, theme: dict, demo_data: dict | None = None) -> html.Div:
    """Onglet IA : appelle l'API FastAPI et affiche la classification thermique."""

    # ── Résolution des valeurs (démo ou simulateur) ──────────
    d      = demo_data or {}
    active = d.get('active', False)

    delta     = d.get('delta',     state.get('temp_process_delta', 10.0)) if active else state.get('temp_process_delta', 10.0)
    nb_pannes = int(d.get('nb_pannes', state.get('nb_pannes_7j', 0)))     if active else int(state.get('nb_pannes_7j', 0))
    usure     = d.get('usure',     state.get('usure_cumulee_pct', 42.0))  if active else state.get('usure_cumulee_pct', 42.0)

    # ── Panneau Démonstration ─────────────────────────────────
    demo_color  = theme.get('accent_purple', '#8b5cf6')
    toggle_bg   = _rgba(demo_color, 0.18) if active else _rgba(theme['text_muted'], 0.10)
    toggle_text = '● DÉMO ACTIF' if active else '○ Mode Simulateur'
    toggle_col  = demo_color if active else theme['text_muted']

    def _slider(label, sid, mn, mx, step, val, fmt='{:.1f}'):
        return html.Div(style={'display': 'flex', 'flexDirection': 'column', 'gap': '4px'}, children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
                html.Span(label, style={'fontSize': '11px', 'color': theme['text_secondary'], 'fontWeight': '600'}),
                html.Span(fmt.format(val), style={'fontSize': '11px', 'color': demo_color, 'fontWeight': '700'}),
            ]),
            dcc.Slider(
                id=sid, min=mn, max=mx, step=step, value=val,
                marks=None, tooltip={'always_visible': False},
                updatemode='drag',
            ),
        ])

    def _preset_btn(label, bid, color):
        return html.Button(label, id=bid, n_clicks=0, style={
            'fontSize': '11px', 'fontWeight': '700', 'padding': '6px 14px',
            'borderRadius': '999px', 'border': f'1px solid {_rgba(color, 0.4)}',
            'background': _rgba(color, 0.12), 'color': color, 'cursor': 'pointer',
        })

    demo_panel = html.Div(className='panel', style={'marginBottom': '14px'}, children=[
        html.Div(className='panel-head', children=[
            html.Div(children=[
                html.Div('Mode Démonstration', className='panel-title'),
                html.Div('Simulation manuelle de pannes thermiques en temps réel',
                         className='panel-subtitle'),
            ]),
            html.Button(
                toggle_text, id='demo-toggle-B', n_clicks=0,
                style={
                    'fontSize': '11px', 'fontWeight': '700', 'padding': '5px 16px',
                    'borderRadius': '999px', 'border': f'1px solid {_rgba(toggle_col, 0.4)}',
                    'background': toggle_bg, 'color': toggle_col, 'cursor': 'pointer',
                },
            ),
        ]),
        html.Div(style={'padding': '16px', 'display': 'flex', 'flexDirection': 'column', 'gap': '14px'}, children=[
            # Scénarios prédéfinis
            html.Div(style={'display': 'flex', 'gap': '8px', 'flexWrap': 'wrap'}, children=[
                html.Span('Scénarios :', style={'fontSize': '11px', 'color': theme['text_muted'],
                                                'alignSelf': 'center', 'fontWeight': '600'}),
                _preset_btn('Normal',            'demo-btn-normal-B',   theme['ok']),
                _preset_btn('Surchauffe',        'demo-btn-warning-B',  theme['warning']),
                _preset_btn('🔥 PANNE IMMINENTE', 'demo-btn-critique-B', theme['critical']),
            ]),
            # Sliders
            html.Div(style={
                'display': 'grid', 'gridTemplateColumns': '1fr 1fr 1fr', 'gap': '16px',
                'opacity': '1' if active else '0.45',
                'pointerEvents': 'auto' if active else 'none',
            }, children=[
                _slider('Delta thermique (K)', 'demo-slider-delta-B',    5,  30, 0.5, delta,     '{:.1f} K'),
                _slider('Pannes 7 jours',      'demo-slider-pannes-B',   0,  20, 1,   nb_pannes, '{:.0f}'),
                _slider('Usure outil (%)',      'demo-slider-usure-B',    0, 100, 1,   usure,     '{:.0f}%'),
            ]),
            html.Div(
                '☝ Active le mode démo puis déplace les curseurs — la prédiction se met à jour en temps réel' if not active
                else '✓ Mode démo actif — les curseurs remplacent les données du simulateur',
                style={'fontSize': '10px', 'color': toggle_col, 'fontStyle': 'italic'},
            ),
        ]),
    ])

    # ── Appel API ────────────────────────────────────────────
    api_ok     = False
    label      = None
    nom        = ''
    probas     = {}
    alerte     = 'OK'
    interpreta = ''
    modele_info= ''
    err_msg    = ''

    payload = {
        'temp_process_delta'      : delta,
        'TRS'                     : state.get('TRS', 0.9),
        'taux_rebut'              : state.get('taux_rebut', 0.03),
        'disponibilite'           : state.get('disponibilite', 1.0),
        'performance'             : state.get('performance', 1.0),
        'consommation_kwh'        : state.get('consommation_kwh', 3.5),
        'temps_cycle_min'         : state.get('temps_cycle_min', 40.0),
        'derive_cycle_pct'        : state.get('derive_cycle_pct', 0.0),
        'nb_pannes_7j'            : nb_pannes,
        'temp_process_c'          : state.get('temp_process_c', 34.0),
        'usure_cumulee_pct'       : usure,
        'couple_nm'               : state.get('couple_nm', 45.0),
        'vitesse_rotation_rpm'    : state.get('vitesse_rotation_rpm', 1530),
        'indice_stabilite_process': state.get('indice_stabilite_process', 0.9),
        'panne_usure_outil'       : int(state.get('panne_usure_outil', 0)),
    }

    try:
        resp = requests.post(_AI_API_URL_B, json=payload, timeout=2)
        if resp.status_code == 200:
            data        = resp.json()
            api_ok      = True
            label       = data.get('risque_label', 0)
            nom         = data.get('risque_nom', 'Normal')
            probas      = data.get('probabilites', {})
            alerte      = data.get('niveau_alerte', 'OK')
            interpreta  = data.get('interpretation', '')
            modele_info = data.get('modele', '')
        else:
            err_msg = f"API erreur {resp.status_code}"
    except Exception as e:
        err_msg = f"API indisponible — lancez l'API sur le port 8000 ({type(e).__name__})"

    # ── Couleurs ─────────────────────────────────────────────
    alerte_color = {
        'CRITICAL': theme['critical'],
        'WARNING' : theme['warning'],
        'OK'      : theme['ok'],
    }.get(alerte, theme['text_muted'])
    alerte_bg = _rgba(alerte_color, 0.12)

    # ── Graphique probabilités ────────────────────────────────
    if api_ok and probas:
        classes = ['Normal', 'Risque', 'Critique']
        vals    = [probas.get(c, 0) for c in classes]
        bar_colors = [theme['ok'], theme['warning'], theme['critical']]

        fig_proba = go.Figure()
        for c, v, col in zip(classes, vals, bar_colors):
            fig_proba.add_trace(go.Bar(
                name=c, x=[c], y=[v * 100],
                marker_color=col,
                marker_opacity=0.8,
                text=[f'{v*100:.1f}%'],
                textposition='outside',
                textfont={'size': 11, 'color': col},
            ))
        layout_p = _plot_layout(theme, title='Probabilités par classe (%)', height=240)
        layout_p['margin']      = dict(l=20, r=20, t=50, b=30)
        layout_p['showlegend'] = False
        layout_p['yaxis']      = {**_axis(theme, '%'), 'range': [0, 115]}
        layout_p['xaxis']      = _axis(theme)
        layout_p['barmode']    = 'group'
        fig_proba.update_layout(layout_p)
        proba_el = dcc.Graph(figure=fig_proba, config={'displayModeBar': False})
    else:
        proba_el = html.Div(
            err_msg or 'Données indisponibles',
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
            html.Span('●', style={'color': alerte_color, 'fontSize': '10px'}),
            html.Span(alerte, style={
                'fontSize': '11px', 'fontWeight': '800', 'color': alerte_color,
                'padding': '3px 10px', 'borderRadius': '999px',
                'background': alerte_bg, 'border': f'1px solid {_rgba(alerte_color, 0.3)}',
            }),
        ]) if api_ok else html.Div(),

        # Classe prédite
        html.Div(style={
            'background': theme['bg_card'], 'borderRadius': '16px',
            'padding': '20px', 'textAlign': 'center',
            'border': f"2px solid {alerte_color if api_ok else theme['border']}",
        }, children=[
            html.Div('Classe prédite', style={'fontSize': '10px', 'color': theme['text_muted'],
                                              'textTransform': 'uppercase', 'fontWeight': '700'}),
            html.Div(nom if api_ok else '—', style={
                'fontSize': '28px', 'fontWeight': '900',
                'color': alerte_color if api_ok else theme['text_muted'],
                'marginTop': '6px',
            }),
            html.Div(
                f'label {label}' if api_ok else '',
                style={'fontSize': '10px', 'color': theme['text_muted'], 'marginTop': '4px'},
            ),
        ]) if api_ok else html.Div(
            err_msg,
            style={'fontSize': '12px', 'color': theme['critical'],
                   'fontStyle': 'italic', 'padding': '10px'},
        ),

        # Interprétation
        html.Div(interpreta if api_ok else '', style={
            'fontSize': '12px', 'color': theme['text_secondary'],
            'lineHeight': '1.6', 'fontStyle': 'italic',
        }),
    ])

    # ── Données d'entrée ──────────────────────────────────────
    def chip(label, value, highlight=False):
        return html.Div(style={
            'padding': '8px 12px', 'background': theme['bg_surface'],
            'borderRadius': '8px', 'border': f"1px solid {theme['border']}",
            'borderLeft': f"3px solid {theme['accent_cyan']}" if highlight else '',
        }, children=[
            html.Div(label, style={'fontSize': '9px', 'color': theme['text_muted'],
                                   'textTransform': 'uppercase', 'fontWeight': '700'}),
            html.Div(str(value), style={'fontSize': '13px', 'fontWeight': '700',
                                        'color': theme['accent_cyan'] if highlight else theme['text_primary']}),
        ])

    input_row = html.Div(style={
        'display': 'grid', 'gridTemplateColumns': 'repeat(4, 1fr)', 'gap': '8px',
    }, children=[
        chip('Delta thermique', f"{payload['temp_process_delta']:.1f} K", highlight=True),
        chip('Temp process',    f"{payload['temp_process_c']:.1f} °C"),
        chip('TRS',             f"{payload['TRS']*100:.1f}%"),
        chip('Usure outil',     f"{payload['usure_cumulee_pct']:.1f}%"),
        chip('Couple',          f"{payload['couple_nm']:.1f} N·m"),
        chip('Vitesse',         f"{int(payload['vitesse_rotation_rpm'])} rpm"),
        chip('Stabilité',       f"{payload['indice_stabilite_process']:.2f}"),
        chip('Pannes 7j',       int(payload['nb_pannes_7j'])),
    ])

    source_badge = html.Div(
        '🎮 DÉMO' if active else '📡 Simulateur',
        style={
            'fontSize': '10px', 'fontWeight': '700', 'padding': '3px 10px',
            'borderRadius': '999px',
            'color': demo_color if active else theme['text_muted'],
            'background': _rgba(demo_color if active else theme['text_muted'], 0.10),
            'border': f"1px solid {_rgba(demo_color if active else theme['text_muted'], 0.25)}",
        },
    )

    return html.Div(children=[
        demo_panel,
        html.Div(className='panel', style={'marginBottom': '14px'}, children=[
            html.Div(className='panel-head', children=[
                html.Div(children=[
                    html.Div('AI · Maintenance Prédictive — Risque Thermique', className='panel-title'),
                    html.Div(
                        f'Classification {modele_info}' if api_ok
                        else 'Classification · EasyEnsembleClassifier · RecallCritique=0.375',
                        className='panel-subtitle',
                    ),
                ]),
                html.Div(style={'display': 'flex', 'gap': '8px', 'alignItems': 'center'}, children=[
                    source_badge,
                    html.Div('MSPR 841', style={
                        'fontSize': '10px', 'fontWeight': '700', 'padding': '3px 10px',
                        'borderRadius': '999px', 'color': theme['accent_purple'],
                        'background': _rgba(theme['accent_purple'], 0.10),
                        'border': f"1px solid {_rgba(theme['accent_purple'], 0.25)}",
                    }),
                ]),
            ]),
            html.Div(style={
                'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                'gap': '16px', 'padding': '16px',
            }, children=[
                proba_el,
                result_card,
            ]),
        ]),
        html.Div(className='panel', style={'padding': '16px'}, children=[
            html.Div('Données d\'entrée · Session courante', className='panel-title',
                     style={'marginBottom': '12px'}),
            input_row,
            html.Div(
                '⚠ Mode single-session : features de lag/rolling approximées. '
                'Modèle entraîné sur données simulées — recalibration terrain recommandée.',
                style={'fontSize': '10px', 'color': theme['text_muted'],
                       'marginTop': '10px', 'fontStyle': 'italic'},
            ),
        ]),
    ])


# ─────────────────────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────────────────────
app.layout = html.Div(
    id='root-B',
    style={'minHeight': '100vh'},
    children=[
        dcc.Interval(id='interval-B', interval=1000, n_intervals=0),
        dcc.Store(id='tab-store-B', data='overview'),
        dcc.Store(id='demo-store-B', data={
            'active': False, 'delta': 9.5, 'nb_pannes': 0, 'usure': 42.0,
        }),
        html.Div(id='page-content-B'),
        html.Div(id='tab-bar-container-B'),
    ]
)

# ─────────────────────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('tab-store-B', 'data'),
    Input('tab-btn-overview-B',    'n_clicks'),
    Input('tab-btn-maintenance-B', 'n_clicks'),
    Input('tab-btn-quality-B',     'n_clicks'),
    Input('tab-btn-alerts-B',      'n_clicks'),
    Input('tab-btn-ai-B',          'n_clicks'),
    prevent_initial_call=True,
)
def switch_tab_B(n1, n2, n3, n4, n5):
    mapping = {
        'tab-btn-overview-B'    : 'overview',
        'tab-btn-maintenance-B' : 'maintenance',
        'tab-btn-quality-B'     : 'quality',
        'tab-btn-alerts-B'      : 'alerts',
        'tab-btn-ai-B'          : 'ai',
    }
    return mapping.get(ctx.triggered_id, 'overview')


@app.callback(
    Output('tab-bar-container-B', 'children'),
    Input('tab-store-B', 'data'),
)
def update_tab_bar_B(active_tab):
    theme = _soft_theme(DEFAULT_THEME_MODE)

    def tab_btn(label, tab_id, btn_id):
        is_active = active_tab == tab_id
        return html.Button(label, id=btn_id, n_clicks=0, style={
            'background' : _rgba(theme['accent_blue'], 0.12) if is_active else 'transparent',
            'border'     : f"1px solid {_rgba(theme['accent_blue'], 0.25) if is_active else theme['border']}",
            'color'      : theme['accent_blue'] if is_active else theme['text_muted'],
            'borderRadius': '10px', 'padding': '6px 16px', 'fontSize': '11px',
            'fontWeight' : '700', 'cursor': 'pointer',
            'fontFamily' : 'Inter, sans-serif',
        })

    return html.Div(style={
        'display'      : 'flex',
        'gap'          : '8px',
        'padding'      : '10px 22px',
        'borderBottom' : f"1px solid {theme['border']}",
        'background'   : theme.get('bg_sidebar', theme['bg_card']),
        'position'     : 'sticky',
        'top'          : '57px',
        'zIndex'       : '15',
    }, children=[
        tab_btn('Overview',       'overview',    'tab-btn-overview-B'),
        tab_btn('Maintenance',    'maintenance', 'tab-btn-maintenance-B'),
        tab_btn('Quality',        'quality',     'tab-btn-quality-B'),
        tab_btn('Alerts',         'alerts',      'tab-btn-alerts-B'),
        tab_btn('AI Predictions', 'ai',          'tab-btn-ai-B'),
    ])


@app.callback(
    Output('page-content-B', 'children'),
    Input('interval-B', 'n_intervals'),
    State('tab-store-B', 'data'),
    State('demo-store-B', 'data'),
)
def update_page_B(n, active_tab, demo_data):
    ensure_simulator_started()
    theme      = _soft_theme(DEFAULT_THEME_MODE)
    state      = store.get_current_state(USINE_ID)
    aggs       = store.get_aggregations(USINE_ID)
    all_alts   = store.get_active_alerts(USINE_ID)
    persistent = _get_persistent_alerts(all_alts)

    ts_str = 'N/A'
    sim    = store.get_sim_state(USINE_ID)
    ts     = sim.get('timestamp_simule')
    if ts and hasattr(ts, 'strftime'):
        ts_str = ts.strftime('%d %b %Y · %H:%M')

    if active_tab == 'maintenance':
        tab_content = build_tab_maintenance(state, theme)
    elif active_tab == 'quality':
        tab_content = build_tab_quality(state, theme)
    elif active_tab == 'alerts':
        tab_content = build_tab_alerts(theme)
    elif active_tab == 'ai':
        tab_content = build_tab_ai_B(state, theme, demo_data or {})
    else:
        tab_content = build_tab_overview(state, aggs, theme)

    return html.Div(
        className='theme-root',
        style=_theme_vars(theme),
        children=[html.Div(className='app-shell', children=[
            build_sidebar(theme),
            html.Div(className='main-panel', children=[
                build_topbar(theme, ts_str),
                html.Div(className='page-wrap', children=[
                    build_hero(theme, ts_str),
                    build_alert_banner(persistent, theme),
                    build_kpi_strip(state, aggs, theme),
                    tab_content,
                    html.Div(
                        f"MECHA Monitoring System · Site {USINE_ID} · Port {PORT}",
                        className='footer-note'
                    ),
                ]),
            ]),
        ])],
    )


# ─────────────────────────────────────────────────────────────
# CALLBACK DÉMO — mise à jour du store via toggle / presets / sliders
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('demo-store-B', 'data'),
    Input('demo-toggle-B',       'n_clicks'),
    Input('demo-btn-normal-B',   'n_clicks'),
    Input('demo-btn-warning-B',  'n_clicks'),
    Input('demo-btn-critique-B', 'n_clicks'),
    Input('demo-slider-delta-B',  'value'),
    Input('demo-slider-pannes-B', 'value'),
    Input('demo-slider-usure-B',  'value'),
    State('demo-store-B', 'data'),
    prevent_initial_call=True,
)
def update_demo_store_B(toggle, normal, warning, critique, delta, nb_pannes, usure, current):
    triggered = ctx.triggered_id
    d = dict(current) if current else {'active': False, 'delta': 9.5, 'nb_pannes': 0, 'usure': 42.0}

    if triggered == 'demo-toggle-B':
        d['active'] = not d.get('active', False)

    elif triggered == 'demo-btn-normal-B':
        d.update({'active': True, 'delta': 8.0,  'nb_pannes': 0,  'usure': 30.0})

    elif triggered == 'demo-btn-warning-B':
        d.update({'active': True, 'delta': 16.0, 'nb_pannes': 5,  'usure': 65.0})

    elif triggered == 'demo-btn-critique-B':
        d.update({'active': True, 'delta': 24.0, 'nb_pannes': 12, 'usure': 88.0})

    elif triggered in ('demo-slider-delta-B', 'demo-slider-pannes-B', 'demo-slider-usure-B'):
        d['active'] = True
        if delta     is not None: d['delta']     = float(delta)
        if nb_pannes is not None: d['nb_pannes'] = int(nb_pannes)
        if usure     is not None: d['usure']     = float(usure)

    return d


if __name__ == '__main__':
    ensure_simulator_started()
    app.run(debug=False, port=PORT, host='0.0.0.0')