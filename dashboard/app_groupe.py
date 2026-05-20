# ============================================================
# app_groupe.py — MECHA Group Monitoring Dashboard
#
# Enterprise UI / UX
# Logic preserved
# - store / simulator / kpi_engine untouched
# - KPI calculations untouched
# - CSS loaded from assets/app.css
#
# THEME CONTROL:
# Change DEFAULT_THEME_MODE below to 'dark' or 'light'
# ============================================================

import threading
import time
from datetime import datetime

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go

import store
import kpi_engine
import simulator
from config import (
    USINES, USINE_LABELS, USINE_PORTS,
    USINE_DOMINANT_PROBLEM,
    get_theme,
)

# ─────────────────────────────────────────────────────────────
# THEME CONTROL
# ─────────────────────────────────────────────────────────────
DEFAULT_THEME_MODE = 'dark'   # 'dark' or 'light'

# ─────────────────────────────────────────────────────────────
# INITIALISATION DASH
# ─────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title='MECHA Group Monitoring',
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
    'CRITICAL': 999999,
    'WARNING': 10,
    'INFO': 6,
}


def ensure_simulator_started():
    global _sim_started
    with _sim_lock:
        if not _sim_started:
            simulator.start()
            _sim_started = True


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _safe_text(value: str) -> str:
    if not value:
        return ""
    txt = str(value).replace("_", " ").replace("—", "·").strip()
    while "  " in txt:
        txt = txt.replace("  ", " ")
    return txt


def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def _fmt_pct_int(val: float) -> str:
    return f"{val * 100:.0f}%"


def _fmt_trs_color(trs: float, theme: dict) -> str:
    if trs >= 0.90:
        return theme['ok']
    if trs >= 0.80:
        return theme['warning']
    return theme['critical']


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return f'rgba(255,255,255,{alpha})'
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def _soft_theme(mode: str) -> dict:
    base = get_theme(mode or 'dark')

    if mode == 'light':
        premium = {
            'bg_primary': '#f4f6f8',
            'bg_secondary': '#e9edf2',
            'bg_card': 'rgba(255,255,255,0.96)',
            'bg_surface': '#f8fafc',
            'bg_sidebar': 'rgba(255,255,255,0.94)',
            'text_primary': '#101828',
            'text_secondary': '#475467',
            'text_muted': '#667085',
            'border': 'rgba(16,24,40,0.08)',
            'accent_blue': '#315ea8',
            'accent_purple': '#4f5f9f',
            'accent_cyan': '#3f7f8f',
            'accent_green': '#2e8b57',
            'accent_orange': '#b7791f',
            'ok': '#2f855a',
            'warning': '#b7791f',
            'critical': '#b54747',
            'chart_fill': 'rgba(49,94,168,0.10)',
            'glass': 'rgba(255,255,255,0.72)',
        }
    else:
        premium = {
            'bg_primary': '#071018',
            'bg_secondary': '#0b1620',
            'bg_card': 'rgba(15, 24, 34, 0.97)',
            'bg_surface': '#111c28',
            'bg_sidebar': 'rgba(10, 18, 27, 0.98)',
            'text_primary': '#ecf2f8',
            'text_secondary': '#b0bcc9',
            'text_muted': '#7d8a98',
            'border': 'rgba(255,255,255,0.07)',
            'accent_blue': '#5b7fa3',
            'accent_purple': '#6b7394',
            'accent_cyan': '#5b8f95',
            'accent_green': '#4d8c6f',
            'accent_orange': '#b68a52',
            'ok': '#4d8c6f',
            'warning': '#b68a52',
            'critical': '#b85c5c',
            'chart_fill': 'rgba(91,127,163,0.10)',
            'glass': 'rgba(255,255,255,0.025)',
        }

    return {**base, **premium}


def _theme_vars(theme: dict) -> dict:
    return {
        '--bg-primary': theme['bg_primary'],
        '--bg-secondary': theme.get('bg_secondary', theme['bg_primary']),
        '--bg-card': theme['bg_card'],
        '--bg-surface': theme['bg_surface'],
        '--bg-sidebar': theme.get('bg_sidebar', theme['bg_card']),
        '--text-primary': theme['text_primary'],
        '--text-secondary': theme['text_secondary'],
        '--text-muted': theme['text_muted'],
        '--border': theme['border'],
        '--accent-blue': theme['accent_blue'],
        '--accent-purple': theme['accent_purple'],
        '--accent-cyan': theme.get('accent_cyan', theme['accent_blue']),
        '--accent-green': theme.get('accent_green', theme['ok']),
        '--accent-orange': theme.get('accent_orange', theme['warning']),
        '--ok': theme['ok'],
        '--warning': theme['warning'],
        '--critical': theme['critical'],
        '--chart-fill': theme['chart_fill'],
        '--glass': theme.get('glass', 'rgba(255,255,255,0.04)'),
    }


def _statut_config(statut: str, theme: dict) -> dict:
    mapping = {
        'CRITICAL': {
            'color': theme['critical'],
            'bg': _rgba(theme['critical'], 0.12),
            'border': _rgba(theme['critical'], 0.28),
            'label': 'Critical',
            'dot': theme['critical'],
        },
        'WARNING': {
            'color': theme['warning'],
            'bg': _rgba(theme['warning'], 0.12),
            'border': _rgba(theme['warning'], 0.28),
            'label': 'Attention',
            'dot': theme['warning'],
        },
        'OK': {
            'color': theme['ok'],
            'bg': _rgba(theme['ok'], 0.12),
            'border': _rgba(theme['ok'], 0.22),
            'label': 'Normal',
            'dot': theme['ok'],
        },
        'INIT': {
            'color': theme['text_muted'],
            'bg': _rgba('#94a3b8', 0.10),
            'border': theme['border'],
            'label': 'Initializing',
            'dot': theme['text_muted'],
        },
    }
    return mapping.get(statut, {
        'color': theme['text_muted'],
        'bg': _rgba('#94a3b8', 0.08),
        'border': theme['border'],
        'label': _safe_text(statut).title(),
        'dot': theme['text_muted'],
    })


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
        if sev == 'CRITICAL' or (now - item['timestamp'] <= ttl):
            visible.append(item)
        else:
            del _ALERT_MEMORY[key]

    priority = {'CRITICAL': 0, 'WARNING': 1, 'INFO': 2}
    visible.sort(key=lambda x: priority.get(x['severity'], 3))
    return visible


# ─────────────────────────────────────────────────────────────
# VISUAL ELEMENTS
# ─────────────────────────────────────────────────────────────
def logo_mark():
    return html.Div(
        className="brand-logo",
        children=[
            html.Div(className="brand-logo-stem brand-logo-stem-left"),
            html.Div(className="brand-logo-stem brand-logo-stem-mid"),
            html.Div(className="brand-logo-stem brand-logo-stem-right"),
        ]
    )


def nav_icon(active=False):
    return html.Div(
        className=f"nav-pill {'active' if active else ''}",
        children=[html.Div(className="nav-icon")]
    )


# ─────────────────────────────────────────────────────────────
# TOPBAR + SIDEBAR
# ─────────────────────────────────────────────────────────────
def build_sidebar(theme: dict) -> html.Div:
    return html.Div(
        className='sidebar',
        children=[
            html.Div(
                className='sidebar-top',
                children=[
                    html.Div(
                        className='brand-lockup',
                        children=[
                            logo_mark(),
                            html.Div("MECHA", className='brand-text')
                        ]
                    ),
                    html.Div(
                        className='nav-stack',
                        children=[
                            nav_icon(active=True),
                            nav_icon(),
                            nav_icon(),
                            nav_icon(),
                            nav_icon(),
                        ]
                    )
                ]
            ),
            html.Div(
                className='nav-stack',
                children=[nav_icon()]
            )
        ]
    )


def build_topbar(theme: dict, ts_simule: str) -> html.Div:
    now_real = datetime.now().strftime('%d %b %Y · %H:%M:%S')
    return html.Div(
        className='topbar',
        children=[
            html.Div(
                className='topbar-left',
                children=[
                    html.Div(
                        className='search-shell',
                        children=[
                            html.Div(className='search-dot'),
                            html.Div(
                                f"Quick search · {ts_simule}",
                                className='search-text'
                            )
                        ]
                    )
                ]
            ),
            html.Div(
                className='topbar-right',
                children=[
                    html.Div("⟳", className='icon-btn'),
                    html.Div("✦", className='icon-btn'),
                    html.Div(
                        className='profile-chip',
                        children=[
                            html.Div("M", className='avatar'),
                            html.Div(
                                className='profile-meta',
                                children=[
                                    html.Div("MECHA Ops", className='profile-name'),
                                    html.Div(now_real, className='profile-role')
                                ]
                            )
                        ]
                    )
                ]
            )
        ]
    )


# ─────────────────────────────────────────────────────────────
# HERO + ALERTS + KPI STRIP
# ─────────────────────────────────────────────────────────────
def build_alert_banner(persistent_alerts, theme: dict) -> html.Div:
    if not persistent_alerts:
        return html.Div()

    top = persistent_alerts[0]
    sev = top['severity']

    styles = {
        'CRITICAL': {
            'border': _rgba(theme['critical'], 0.24),
            'bg': f"linear-gradient(90deg, {_rgba(theme['critical'], 0.12)}, {_rgba(theme['critical'], 0.04)})",
            'icon_bg': _rgba(theme['critical'], 0.14),
            'color': theme['critical'],
            'label': 'Critical',
        },
        'WARNING': {
            'border': _rgba(theme['warning'], 0.24),
            'bg': f"linear-gradient(90deg, {_rgba(theme['warning'], 0.10)}, {_rgba(theme['warning'], 0.04)})",
            'icon_bg': _rgba(theme['warning'], 0.14),
            'color': theme['warning'],
            'label': 'Warning',
        },
        'INFO': {
            'border': _rgba(theme['accent_blue'], 0.24),
            'bg': f"linear-gradient(90deg, {_rgba(theme['accent_blue'], 0.10)}, {_rgba(theme['accent_blue'], 0.04)})",
            'icon_bg': _rgba(theme['accent_blue'], 0.14),
            'color': theme['accent_blue'],
            'label': 'Info',
        },
    }[sev]

    messages = " · ".join([a['message'] for a in persistent_alerts[:3]])

    return html.Div(
        className='alert-banner',
        style={
            'borderColor': styles['border'],
            'background': styles['bg'],
        },
        children=[
            html.Div(
                styles['label'][0],
                className='alert-icon',
                style={
                    'background': styles['icon_bg'],
                    'color': styles['color'],
                }
            ),
            html.Div(messages, className='alert-text', style={'color': styles['color']}),
        ]
    )


def build_hero(theme: dict, ts_simule: str, summaries: list) -> html.Div:
    nb_sites = len(summaries)
    return html.Div(
        className='page-hero',
        children=[
            html.Div(
                children=[
                    html.Div("Executive Overview", className='eyebrow'),
                    html.H1("Group Performance Command", className='hero-title'),
                    html.Div(
                        "A fast executive view of industrial health, priority alerts, and site performance.",
                        className='hero-subtitle'
                    ),
                    html.Div(
                        className='meta-row',
                        children=[
                            html.Div(
                                className='meta-badge',
                                children=[
                                    html.Div(className='live-dot'),
                                    html.Span("Simulation live")
                                ]
                            ),
                            html.Div(
                                className='meta-badge',
                                children=[html.Span(f"{nb_sites} sites monitored")]
                            ),
                            html.Div(
                                className='meta-badge',
                                children=[html.Span(f"Simulated time {ts_simule}")]
                            )
                        ]
                    )
                ]
            ),
            html.Div(
                className='hero-actions',
                children=[
                    html.Button("Operations center", className='primary-btn'),
                    html.Button("Compact view", className='ghost-btn')
                ]
            )
        ]
    )


def build_exec_kpi_strip(summaries: list, critiques, theme: dict) -> html.Div:
    trs_values = [s.get('TRS_courant', 0.0) for s in summaries]
    avg_trs = sum(trs_values) / len(trs_values) if trs_values else 0.0
    total_alerts = sum(s.get('nb_alertes', 0) for s in summaries)
    avg_rebut = sum(s.get('taux_rebut', 0.0) for s in summaries) / len(summaries) if summaries else 0.0
    nb_critical_sites = len([s for s in summaries if s.get('statut_global') == 'CRITICAL'])

    items = [
        {
            "title": "Group TRS",
            "value": _fmt_pct(avg_trs),
            "sub": f"{len(summaries)} sites consolidated",
            "color": _fmt_trs_color(avg_trs, theme),
            "bar": avg_trs,
            "icon_bg": _rgba(theme['accent_blue'], 0.14),
            "icon_fg": theme['accent_blue'],
            "icon": "◌",
        },
        {
            "title": "Active alerts",
            "value": str(total_alerts),
            "sub": f"{len(critiques)} critical in progress",
            "color": theme['critical'] if total_alerts > 0 else theme['text_primary'],
            "bar": min(total_alerts / 12, 1),
            "icon_bg": _rgba(theme['critical'], 0.14),
            "icon_fg": theme['critical'],
            "icon": "!",
        },
        {
            "title": "Average scrap",
            "value": _fmt_pct(avg_rebut),
            "sub": "Rolling group average",
            "color": theme['warning'] if avg_rebut > 0.05 else theme['text_primary'],
            "bar": min(avg_rebut * 4, 1),
            "icon_bg": _rgba(theme['accent_orange'], 0.14),
            "icon_fg": theme['accent_orange'],
            "icon": "○",
        },
        {
            "title": "Critical sites",
            "value": str(nb_critical_sites),
            "sub": "Supervision priority",
            "color": theme['critical'] if nb_critical_sites > 0 else theme['ok'],
            "bar": min(nb_critical_sites / max(len(summaries), 1), 1),
            "icon_bg": _rgba(theme['accent_purple'], 0.14),
            "icon_fg": theme['accent_purple'],
            "icon": "✦",
        },
    ]

    cards = []
    for item in items:
        cards.append(
            html.Div(
                className='metric-card',
                children=[
                    html.Div(
                        className='metric-top',
                        children=[
                            html.Div(
                                children=[
                                    html.Div(item['title'], className='metric-title'),
                                    html.Div(
                                        item['value'],
                                        className='metric-value',
                                        style={'color': item['color']}
                                    ),
                                    html.Div(item['sub'], className='metric-sub')
                                ]
                            ),
                            html.Div(
                                item['icon'],
                                className='metric-icon',
                                style={
                                    'background': item['icon_bg'],
                                    'color': item['icon_fg'],
                                }
                            )
                        ]
                    ),
                    html.Div(
                        className='metric-bar',
                        children=[
                            html.Div(
                                className='metric-bar-fill',
                                style={
                                    'width': f"{max(0, min(item['bar'], 1)) * 100:.0f}%",
                                    'background': f"linear-gradient(90deg, {item['icon_fg']}, {theme['accent_purple']})"
                                }
                            )
                        ]
                    )
                ]
            )
        )

    return html.Div(className='kpi-strip', children=cards)


# ─────────────────────────────────────────────────────────────
# CHARTS / CARDS
# ─────────────────────────────────────────────────────────────
def build_sparkline(trs_values: list, theme: dict) -> dcc.Graph:
    if not trs_values:
        trs_values = [0.0]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=trs_values,
        mode='lines',
        line=dict(color=theme['accent_blue'], width=1.9),
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
        height=52,
    )
    return dcc.Graph(
        figure=fig,
        config={'displayModeBar': False, 'staticPlot': True},
        style={'height': '52px'}
    )


def build_dpq_bars(d: float, p: float, q: float, theme: dict) -> html.Div:
    def color_for(value, is_q=False):
        if is_q:
            if value > 0.85:
                return theme['ok']
            if value > 0.75:
                return theme['warning']
            return theme['critical']
        if value > 0.90:
            return theme['ok']
        if value > 0.80:
            return theme['warning']
        return theme['critical']

    rows = []
    for label, val, is_q in [('D', d, False), ('P', p, False), ('Q', q, True)]:
        rows.append(
            html.Div(
                className='bar-row',
                children=[
                    html.Div(label, className='bar-label'),
                    html.Div(
                        className='bar-track',
                        children=[
                            html.Div(
                                className='bar-fill',
                                style={
                                    'width': f"{val * 100:.0f}%",
                                    'background': f"linear-gradient(90deg, {color_for(val, is_q)}, {_rgba(color_for(val, is_q), 0.55)})"
                                }
                            )
                        ]
                    ),
                    html.Div(_fmt_pct_int(val), className='bar-value')
                ]
            )
        )
    return html.Div(children=rows)


def build_usine_card(summary: dict, trend_data: dict, theme: dict, port: int) -> html.A:
    usine_id = summary['usine_id']
    statut = summary.get('statut_global', 'INIT')
    cfg = _statut_config(statut, theme)

    trs = summary.get('TRS_courant', 0.0)
    trs_1h = summary.get('TRS_moyen_1h', 0.0)
    rebut = summary.get('taux_rebut', 0.0)
    nb_alert = summary.get('nb_alertes', 0)

    label = _safe_text(USINE_LABELS.get(usine_id, usine_id))
    problem = _safe_text(USINE_DOMINANT_PROBLEM.get(usine_id, ''))
    trs_color = _fmt_trs_color(trs, theme)

    sparkline_vals = trend_data.get('trs_values', [])

    aggs = store.get_aggregations(usine_id).get('1h', {})
    d = aggs.get('disponibilite', 0.0)
    p = aggs.get('performance', 0.0)
    q = aggs.get('qualite', 0.0)

    rebut_color = (
        theme['critical'] if rebut > 0.10 else
        theme['warning'] if rebut > 0.05 else
        theme['text_primary']
    )

    alert_bg = _rgba(theme['critical'], 0.10) if nb_alert > 0 else _rgba('#ffffff', 0.03)

    return html.A(
        href=f"http://localhost:{port}",
        target='_blank',
        children=[
            html.Div(
                className='usine-card',
                children=[
                    html.Div(
                        className='usine-status-line',
                        style={'background': cfg['dot'] if statut in ('CRITICAL', 'WARNING') else 'transparent'}
                    ),

                    html.Div(
                        className='card-top',
                        children=[
                            html.Div(
                                children=[
                                    html.Div(label, className='site-name'),
                                    html.Div(problem, className='site-problem')
                                ]
                            ),
                            html.Div(
                                className='status-pill',
                                style={
                                    'background': cfg['bg'],
                                    'borderColor': cfg['border'],
                                    'color': cfg['color']
                                },
                                children=[
                                    html.Div(className='status-dot', style={'background': cfg['dot']}),
                                    html.Span(cfg['label'])
                                ]
                            )
                        ]
                    ),

                    html.Div(
                        children=[
                            html.Div("TRS", className='trs-label'),
                            html.Div(
                                _fmt_pct(trs),
                                className='trs-value',
                                style={'color': trs_color}
                            ),
                            html.Div(
                                f"1 hour average  {_fmt_pct(trs_1h)}",
                                className='trs-meta'
                            )
                        ]
                    ),

                    html.Div(className='divider'),

                    html.Div(
                        children=[
                            html.Div("TRS breakdown", className='section-caption'),
                            build_dpq_bars(d, p, q, theme)
                        ]
                    ),

                    html.Div(
                        className='mini-grid',
                        children=[
                            html.Div(
                                className='mini-stat',
                                children=[
                                    html.Div("Scrap", className='mini-label'),
                                    html.Div(
                                        _fmt_pct(rebut),
                                        className='mini-value',
                                        style={'color': rebut_color}
                                    )
                                ]
                            ),
                            html.Div(
                                className='mini-stat',
                                style={
                                    'background': alert_bg,
                                    'borderColor': _rgba(theme['critical'], 0.18) if nb_alert > 0 else theme['border']
                                },
                                children=[
                                    html.Div("Alerts", className='mini-label'),
                                    html.Div(
                                        str(nb_alert),
                                        className='mini-value',
                                        style={'color': theme['critical'] if nb_alert > 0 else theme['text_primary']}
                                    )
                                ]
                            ),
                        ]
                    ),

                    html.Div(
                        style={'marginTop': '16px'},
                        children=[
                            html.Div("TRS trend over 1 hour", className='section-caption'),
                            build_sparkline(sparkline_vals, theme)
                        ]
                    ),

                    html.Div(
                        className='trend-foot',
                        children=[
                            html.Div("Open dashboard", className='link-chip')
                        ]
                    )
                ]
            )
        ]
    )


def build_comparison_table(summaries: list, theme: dict) -> html.Div:
    ranked = sorted(
        summaries,
        key=lambda s: s.get('TRS_moyen_1h', 0.0),
        reverse=True
    )

    header = html.Thead(
        html.Tr([
            html.Th("Site"),
            html.Th("TRS 1 hour"),
            html.Th("Current TRS"),
            html.Th("Scrap"),
            html.Th("Alerts"),
            html.Th("Rank"),
        ])
    )

    rows = []
    for i, s in enumerate(ranked):
        agg = store.get_aggregations(s['usine_id']).get('1h', {})
        label = _safe_text(USINE_LABELS.get(s['usine_id'], s['usine_id']))
        trs_1h = agg.get('TRS_moyen', 0.0)
        trs_now = s.get('TRS_courant', 0.0)
        rebut_1h = agg.get('rebut_moyen', 0.0)
        nb_alert = s.get('nb_alertes', 0)
        rang = i + 1

        rank_color = {
            1: '#c3a36a',
            2: '#a8b1be',
            3: '#a87d5a',
        }.get(rang, theme['text_muted'])

        rows.append(
            html.Tr(
                className='compare-row',
                children=[
                    html.Td(label),
                    html.Td(_fmt_pct(trs_1h), style={'color': _fmt_trs_color(trs_1h, theme)}),
                    html.Td(_fmt_pct(trs_now), style={'color': _fmt_trs_color(trs_now, theme)}),
                    html.Td(
                        _fmt_pct(rebut_1h),
                        style={
                            'color': (
                                theme['critical'] if rebut_1h > 0.10 else
                                theme['warning'] if rebut_1h > 0.05 else
                                theme['text_primary']
                            )
                        }
                    ),
                    html.Td(
                        str(nb_alert),
                        style={'color': theme['critical'] if nb_alert > 0 else theme['text_muted']}
                    ),
                    html.Td(
                        html.Div(
                            str(rang),
                            className='rank-pill',
                            style={'color': rank_color}
                        )
                    )
                ]
            )
        )

    return html.Div(
        className='panel compare-panel',
        children=[
            html.Div(
                className='compare-header',
                children=[
                    html.Div(
                        className='compare-title-block',
                        children=[
                            html.Div("Site ranking", className='panel-title'),
                            html.Div("Operational performance over the last hour", className='panel-subtitle')
                        ]
                    ),
                    html.Div("⋯", className='panel-menu-btn')
                ]
            ),
            html.Div(
                className='table-shell',
                children=[
                    html.Table(
                        className='compare-table',
                        children=[
                            header,
                            html.Tbody(rows)
                        ]
                    )
                ]
            )
        ]
    )


def build_sites_panel(summaries: list, trends: dict, theme: dict) -> html.Div:
    return html.Div(
        className='panel',
        children=[
            html.Div(
                className='panel-head',
                children=[
                    html.Div(children=[
                        html.Div("Industrial sites", className='panel-title'),
                        html.Div("Consolidated view of operational performance by site", className='panel-subtitle')
                    ]),
                    html.Div("⋯", className='panel-menu-btn')
                ]
            ),
            html.Div(
                className='usines-grid',
                children=[
                    build_usine_card(
                        s,
                        trends[s['usine_id']],
                        theme,
                        USINE_PORTS[s['usine_id']]
                    )
                    for s in summaries
                ]
            )
        ]
    )


def build_summary_side_panel(summaries: list, critiques, theme: dict) -> html.Div:
    ranked = sorted(summaries, key=lambda x: x.get('TRS_moyen_1h', 0.0), reverse=True)
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    def side_stat(title, value, caption, color):
        return html.Div(
            className='metric-card',
            style={'padding': '18px'},
            children=[
                html.Div(title, className='metric-title'),
                html.Div(value, className='metric-value', style={'color': color, 'fontSize': '30px'}),
                html.Div(caption, className='metric-sub')
            ]
        )

    children = []
    if best:
        children.append(side_stat(
            "Top performing site",
            _safe_text(USINE_LABELS.get(best['usine_id'], best['usine_id'])),
            f"1 hour average TRS  {_fmt_pct(best.get('TRS_moyen_1h', 0.0))}",
            theme['ok']
        ))
    if worst:
        children.append(side_stat(
            "Site to watch",
            _safe_text(USINE_LABELS.get(worst['usine_id'], worst['usine_id'])),
            f"1 hour average TRS  {_fmt_pct(worst.get('TRS_moyen_1h', 0.0))}",
            theme['warning'] if worst.get('statut_global') != 'CRITICAL' else theme['critical']
        ))

    children.append(side_stat(
        "Critical alerts",
        str(len(critiques)),
        "Immediate priority level",
        theme['critical'] if len(critiques) > 0 else theme['ok']
    ))

    return html.Div(className='right-stack', children=children)


# ─────────────────────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────────────────────
app.layout = html.Div(
    id='root',
    style={'minHeight': '100vh'},
    children=[
        dcc.Interval(id='interval', interval=1000, n_intervals=0),
        html.Div(id='page-content'),
    ]
)


# ─────────────────────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output('page-content', 'children'),
    Input('interval', 'n_intervals'),
)
def update_page(n):
    ensure_simulator_started()

    theme = _soft_theme(DEFAULT_THEME_MODE)
    summaries = kpi_engine.get_usine_summary()

    for s in summaries:
        agg = store.get_aggregations(s['usine_id']).get('1h', {})
        s['TRS_moyen_1h'] = agg.get('TRS_moyen', 0.0)

    ts_str = 'N/A'
    for usine_id in USINES:
        sim = store.get_sim_state(usine_id)
        ts = sim.get('timestamp_simule')
        if ts and hasattr(ts, 'strftime'):
            ts_str = ts.strftime('%d %b %Y · %H:%M')
            break

    all_alerts = store.get_active_alerts()
    critiques = all_alerts[all_alerts['severite'] == 'CRITICAL'] if not all_alerts.empty else all_alerts
    persistent_alerts = _get_persistent_alerts(all_alerts)

    trends = {
        u: kpi_engine.get_trs_trend(u, n_sessions=48)
        for u in USINES
    }

    page = html.Div(
        className='theme-root',
        style=_theme_vars(theme),
        children=[
            html.Div(
                className='app-shell',
                children=[
                    build_sidebar(theme),
                    html.Div(
                        className='main-panel',
                        children=[
                            build_topbar(theme, ts_str),
                            html.Div(
                                className='page-wrap',
                                children=[
                                    build_hero(theme, ts_str, summaries),
                                    build_alert_banner(persistent_alerts, theme),
                                    build_exec_kpi_strip(summaries, critiques, theme),
                                    html.Div(
                                        className='content-grid',
                                        children=[
                                            html.Div(
                                                children=[
                                                    build_sites_panel(summaries, trends, theme),
                                                    html.Div(style={'height': '16px'}),
                                                    build_comparison_table(summaries, theme),
                                                ]
                                            ),
                                            build_summary_side_panel(summaries, critiques, theme)
                                        ]
                                    ),
                                    html.Div(
                                        "MECHA Monitoring System · Team .J.Innouri · M.Frikha · N. Ben Tama Serroukh",
                                        className='footer-note'
                                    )
                                ]
                            )
                        ]
                    )
                ]
            )
        ]
    )

    return page


# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    ensure_simulator_started()
    app.run(debug=False, port=8050, host='0.0.0.0')