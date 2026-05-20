# ============================================================
# app_usine_C.py — MECHA Site Dashboard · Usine C · Port 8053
# ============================================================

import threading
import time
import json

import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.graph_objects as go

import store
import kpi_engine
import simulator
from config import (
    USINE_LABELS, USINE_DOMINANT_PROBLEM, get_theme,
    TRS_SEUIL_ACCEPTABLE, LIMITS_PATHS,
)

USINE_ID   = 'Usine_C'
PORT       = 8053
SITE_LABEL = USINE_LABELS[USINE_ID]
DOMINANT   = USINE_DOMINANT_PROBLEM[USINE_ID]
DEFAULT_THEME_MODE = 'dark'

app = dash.Dash(__name__, title=f'MECHA · {SITE_LABEL}',
                update_title=None, suppress_callback_exceptions=True,
                assets_folder='assets')
server = app.server

_sim_started = False
_sim_lock    = threading.Lock()

def ensure_simulator_started():
    global _sim_started
    with _sim_lock:
        if not _sim_started:
            simulator.start()
            _sim_started = True

_ALERT_MEMORY = {}
_ALERT_TTL    = {'CRITICAL': 999999, 'WARNING': 10, 'INFO': 6}

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
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f'rgba({r},{g},{b},{alpha})'

def _soft_theme(mode: str) -> dict:
    base = get_theme(mode or 'dark')
    if mode == 'light':
        premium = {
            'bg_primary':'#f4f6f8','bg_secondary':'#e9edf2',
            'bg_card':'rgba(255,255,255,0.96)','bg_surface':'#f8fafc',
            'bg_sidebar':'rgba(255,255,255,0.94)',
            'text_primary':'#101828','text_secondary':'#475467',
            'text_muted':'#667085','border':'rgba(16,24,40,0.08)',
            'accent_blue':'#315ea8','accent_purple':'#4f5f9f',
            'accent_cyan':'#3f7f8f','accent_green':'#2e8b57',
            'accent_orange':'#b7791f','ok':'#2f855a',
            'warning':'#b7791f','critical':'#b54747',
            'chart_fill':'rgba(49,94,168,0.10)',
            'glass':'rgba(255,255,255,0.72)',
        }
    else:
        premium = {
            'bg_primary':'#071018','bg_secondary':'#0b1620',
            'bg_card':'rgba(15,24,34,0.97)','bg_surface':'#111c28',
            'bg_sidebar':'rgba(10,18,27,0.98)',
            'text_primary':'#ecf2f8','text_secondary':'#b0bcc9',
            'text_muted':'#7d8a98','border':'rgba(255,255,255,0.07)',
            'accent_blue':'#5b7fa3','accent_purple':'#6b7394',
            'accent_cyan':'#5b8f95','accent_green':'#4d8c6f',
            'accent_orange':'#b68a52','ok':'#4d8c6f',
            'warning':'#b68a52','critical':'#b85c5c',
            'chart_fill':'rgba(91,127,163,0.10)',
            'glass':'rgba(255,255,255,0.025)',
        }
    return {**base, **premium}

def _theme_vars(theme: dict) -> dict:
    return {
        '--bg-primary':    theme['bg_primary'],
        '--bg-secondary':  theme.get('bg_secondary', theme['bg_primary']),
        '--bg-card':       theme['bg_card'],
        '--bg-surface':    theme['bg_surface'],
        '--bg-sidebar':    theme.get('bg_sidebar', theme['bg_card']),
        '--text-primary':  theme['text_primary'],
        '--text-secondary':theme['text_secondary'],
        '--text-muted':    theme['text_muted'],
        '--border':        theme['border'],
        '--accent-blue':   theme['accent_blue'],
        '--accent-purple': theme['accent_purple'],
        '--accent-cyan':   theme.get('accent_cyan', theme['accent_blue']),
        '--accent-green':  theme.get('accent_green', theme['ok']),
        '--accent-orange': theme.get('accent_orange', theme['warning']),
        '--ok':            theme['ok'],
        '--warning':       theme['warning'],
        '--critical':      theme['critical'],
        '--chart-fill':    theme['chart_fill'],
        '--glass':         theme.get('glass','rgba(255,255,255,0.04)'),
    }

def _statut_config(statut: str, theme: dict) -> dict:
    m = {
        'CRITICAL':{'color':theme['critical'],'bg':_rgba(theme['critical'],0.12),
                    'border':_rgba(theme['critical'],0.28),'label':'Critical','dot':theme['critical']},
        'WARNING': {'color':theme['warning'], 'bg':_rgba(theme['warning'], 0.12),
                    'border':_rgba(theme['warning'], 0.28),'label':'Attention','dot':theme['warning']},
        'OK':      {'color':theme['ok'],      'bg':_rgba(theme['ok'],      0.12),
                    'border':_rgba(theme['ok'],      0.22),'label':'Normal',  'dot':theme['ok']},
        'INIT':    {'color':theme['text_muted'],'bg':_rgba('#94a3b8',0.10),
                    'border':theme['border'],             'label':'Init',     'dot':theme['text_muted']},
    }
    return m.get(statut, {'color':theme['text_muted'],'bg':_rgba('#94a3b8',0.08),
                           'border':theme['border'],'label':statut,'dot':theme['text_muted']})

def _get_persistent_alerts(all_alerts):
    now = time.time()
    if all_alerts is not None and not all_alerts.empty:
        for _, row in all_alerts.iterrows():
            sev = row.get('severite','INFO')
            msg = _safe_text(row.get('message_court',''))
            key = f"{sev}|{msg}"
            _ALERT_MEMORY[key] = {'sev':sev,'msg':msg,'ts':now}
    result, expired = [], []
    for key, data in _ALERT_MEMORY.items():
        age = now - data['ts']
        if age <= _ALERT_TTL.get(data['sev'],6): result.append(data)
        else: expired.append(key)
    for k in expired: del _ALERT_MEMORY[k]
    result.sort(key=lambda x: {'CRITICAL':0,'WARNING':1,'INFO':2}.get(x['sev'],3))
    return result

def _plot_layout(theme: dict, title: str='', height: int=280) -> dict:
    return dict(
        paper_bgcolor=theme.get('paper_bgcolor', theme['bg_card']),
        plot_bgcolor=theme.get('plot_bgcolor',  theme['bg_surface']),
        font=dict(family='Inter, sans-serif', color=theme['text_muted'], size=10),
        margin=dict(l=40,r=16,t=36,b=32), height=height,
        title=dict(text=title, font=dict(size=11,color=theme['text_secondary']),
                   x=0.0, xanchor='left', pad=dict(l=4)),
        showlegend=False, hovermode='x unified',
        hoverlabel=dict(bgcolor=theme['bg_surface'], font_color=theme['text_primary'],
                        font_size=11, bordercolor=theme['border']),
    )

def _axis(theme: dict, title: str='') -> dict:
    return dict(
        gridcolor=theme.get('chart_grid', theme['border']),
        linecolor=theme['border'],
        tickfont=dict(size=9, color=theme['text_muted']),
        title=dict(text=title, font=dict(size=9, color=theme['text_muted'])),
        showgrid=True, zeroline=False,
    )

def _load_limits():
    try:
        with open(LIMITS_PATHS[USINE_ID]) as f: return json.load(f)
    except Exception: return {}

# ── COMPOSANTS COMMUNS ────────────────────────────────────────

def build_sidebar(theme):
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
                html.A(html.Div(className='nav-pill',
                                children=[html.Div(className='nav-icon')]),
                       href='http://localhost:8050', title='Group'),
                html.Div(className='nav-pill active',
                         children=[html.Div(className='nav-icon')]),
            ]),
        ]),
        html.Div(className='sidebar-top', children=[
            html.Div(className='nav-pill', children=[html.Div(className='nav-icon')]),
        ]),
    ])

def build_topbar(theme, ts_str):
    statut   = store.get_current_state(USINE_ID).get('statut_global','INIT')
    sc       = _statut_config(statut, theme)
    nb_alert = store.get_current_state(USINE_ID).get('nb_alertes_actives',0)
    return html.Div(className='topbar', children=[
        html.Div(className='topbar-left', children=[
            html.Div(className='search-shell', children=[
                html.Div(className='search-dot'),
                html.Span(_safe_text(SITE_LABEL), className='search-text'),
            ]),
        ]),
        html.Div(className='topbar-right', children=[
            html.Div(children=[
                html.Span('● ', style={'color':sc['dot'],'fontSize':'8px'}),
                html.Span(sc['label'], style={'fontSize':'11px','color':sc['color'],'fontWeight':'600'}),
            ], style={'display':'flex','alignItems':'center','gap':'4px','padding':'4px 10px',
                      'borderRadius':'999px','border':f"1px solid {sc['border']}",
                      'background':sc['bg']}),
            html.Div(
                f"{'⚠ ' if nb_alert>0 else ''}{nb_alert} alert{'s' if nb_alert!=1 else ''}",
                style={'fontSize':'11px','fontWeight':'600','padding':'4px 10px',
                       'borderRadius':'999px','border':f"1px solid {theme['border']}",
                       'color':theme['critical'] if nb_alert>0 else theme['text_muted'],
                       'background':theme.get('glass','rgba(255,255,255,0.03)')}),
            html.Div(className='profile-chip', children=[
                html.Div('C', className='avatar'),
                html.Div(className='profile-meta', children=[
                    html.Div('Site Manager', className='profile-name'),
                    html.Div(_safe_text(USINE_ID), className='profile-role'),
                ]),
            ]),
        ]),
    ])

def build_hero(theme, ts_str):
    state  = store.get_current_state(USINE_ID)
    trs    = state.get('TRS',0.0)
    statut = state.get('statut_global','INIT')
    sc     = _statut_config(statut, theme)
    return html.Div(className='page-hero', children=[
        html.Div(children=[
            html.Div('INDUSTRIAL SITE', className='eyebrow'),
            html.H1(_safe_text(SITE_LABEL), className='hero-title'),
            html.Div(_safe_text(DOMINANT), className='hero-subtitle'),
            html.Div(className='meta-row', children=[
                html.Div(className='meta-badge',
                         children=[html.Div(className='live-dot'), html.Span('Live monitoring')]),
                html.Div(className='meta-badge',
                         children=[html.Span(f'Simulated time · {ts_str}')]),
                html.Div(className='meta-badge', children=[
                    html.Span(f'TRS · {_fmt_pct(trs)}',
                              style={'color':_fmt_trs_color(trs,theme)})]),
            ]),
        ]),
        html.Div(className='hero-actions', children=[
            html.Div(children=[
                html.Span('● ', style={'color':sc['dot'],'fontSize':'10px'}),
                html.Span(sc['label'], style={'fontWeight':'700'}),
            ], style={'display':'flex','alignItems':'center','gap':'6px',
                      'padding':'8px 16px','borderRadius':'12px',
                      'border':f"1px solid {sc['border']}",
                      'background':sc['bg'],'color':sc['color'],
                      'fontSize':'12px','fontWeight':'700'}),
        ]),
    ])

def build_alert_banner(persistent_alerts, theme):
    if not persistent_alerts: return html.Div()
    top   = persistent_alerts[0]
    sev   = top['sev']
    color = {'CRITICAL':theme['critical'],'WARNING':theme['warning'],
             'INFO':theme.get('accent_cyan',theme['accent_blue'])}.get(sev,theme['text_muted'])
    icon  = {'CRITICAL':'✕','WARNING':'⚠','INFO':'ℹ'}.get(sev,'·')
    extra = f"  +{len(persistent_alerts)-1} more" if len(persistent_alerts)>1 else ""
    return html.Div(className='alert-banner',
                    style={'background':_rgba(color,0.08),'borderColor':_rgba(color,0.22)},
                    children=[
        html.Div(icon, className='alert-icon',
                 style={'background':_rgba(color,0.16),'color':color}),
        html.Div(children=[
            html.Span(_safe_text(top['msg']),
                      style={'color':theme['text_primary'],'fontWeight':'600','fontSize':'12px'}),
            html.Span(extra, style={'color':theme['text_muted'],'fontSize':'11px','marginLeft':'8px'}),
        ]),
    ])

# ── KPI STRIP  (carte 3 = ISP) ────────────────────────────────

def build_kpi_strip(state, aggs, theme):
    trs     = state.get('TRS',0.0)
    rebut   = state.get('taux_rebut',0.0)
    isp     = state.get('indice_stabilite_process',0.0)
    energie = state.get('consommation_kwh',0.0)
    agg_1h  = aggs.get('1h',{})
    trs_1h  = agg_1h.get('TRS_moyen',0.0)
    rebut_1h= agg_1h.get('rebut_moyen',0.0)
    nb_p    = agg_1h.get('nb_pannes',0)
    lim     = _load_limits()
    lwl_isp = lim.get('indice_stabilite_process',{}).get('lwl',0.75)

    def card(title, val, sub, color, bar=None):
        ch = [html.Div(title, className='metric-title'),
              html.Div(val,   className='metric-value', style={'color':color}),
              html.Div(sub,   className='metric-sub')]
        if bar is not None:
            bc = theme['critical'] if bar>90 else theme['warning'] if bar>75 else theme['ok']
            ch.append(html.Div(className='metric-bar', children=[
                html.Div(className='metric-bar-fill',
                         style={'width':f'{min(bar,100):.0f}%','background':bc})]))
        return html.Div(className='metric-card', children=ch)

    isp_c = (theme['critical'] if isp<0.60 else theme['warning'] if isp<lwl_isp else theme['ok'])

    return html.Div(style={
        'display':'grid','gridTemplateColumns':'repeat(4,1fr)',
        'gap':'12px','marginBottom':'16px'}, children=[
        card('TRS Current',     _fmt_pct(trs),   f'1h avg · {_fmt_pct(trs_1h)}',
             _fmt_trs_color(trs,theme), trs*100),
        card('Scrap Rate',      _fmt_pct(rebut),  f'1h avg · {_fmt_pct(rebut_1h)}',
             theme['critical'] if rebut>0.10 else theme['warning'] if rebut>0.07 else theme['ok']),
        card('Process Stability',f'{isp:.3f}',    f'ISP — target > {lwl_isp:.2f}', isp_c),
        card('Energy / session', f'{energie:.2f} kWh', f'{nb_p} failure(s) / 1h', theme['accent_blue']),
    ])

# ── MACHINE GRID ──────────────────────────────────────────────

def build_machine_grid(theme):
    machines = store.get_machine_states(USINE_ID)
    sl = {'EN_PRODUCTION':('Running',theme['ok']),'ARRET':('Stopped',theme['critical']),
          'MAINTENANCE':('Maintenance',theme['warning']),'STANDBY':('Standby',theme['text_muted']),
          'INIT':('Init',theme['text_muted'])}
    cards = []
    for m_id, ms in machines.items():
        statut = ms.get('statut','INIT')
        label, color = sl.get(statut,(statut,theme['text_muted']))
        usure  = ms.get('usure_pct',0.0)
        rebut  = ms.get('taux_rebut',0.0)
        uc     = theme['critical'] if usure>90 else theme['warning'] if usure>75 else theme['ok']
        cards.append(html.Div(style={
            'borderRadius':'14px','border':f"1px solid {theme['border']}",
            'background':theme['bg_surface'],'padding':'14px'}, children=[
            html.Div(style={'display':'flex','justifyContent':'space-between',
                            'alignItems':'center','marginBottom':'10px'}, children=[
                html.Span(m_id, style={'fontWeight':'700','fontSize':'13px',
                                       'color':theme['text_primary']}),
                html.Span(label, style={'fontSize':'10px','fontWeight':'700','color':color,
                                        'padding':'2px 8px','borderRadius':'999px',
                                        'border':f'1px solid {_rgba(color,0.3)}',
                                        'background':_rgba(color,0.1)}),
            ]),
            html.Div(className='bar-row', children=[
                html.Span('W', className='bar-label'),
                html.Div(className='bar-track', children=[
                    html.Div(className='bar-fill',
                             style={'width':f'{min(usure,100):.0f}%','background':uc})]),
                html.Span(f'{usure:.0f}%', className='bar-value'),
            ]),
            html.Div(f'Scrap · {rebut*100:.1f}%',
                     style={'marginTop':'6px','fontSize':'10px','color':theme['text_muted']}),
        ]))
    return html.Div(children=[
        html.Div('Machine Status', style={'fontSize':'11px','fontWeight':'700',
                                          'color':theme['text_muted'],'textTransform':'uppercase',
                                          'letterSpacing':'0.1em','marginBottom':'10px'}),
        html.Div(style={'display':'grid','gridTemplateColumns':'repeat(2,1fr)','gap':'10px'},
                 children=cards),
    ])

# ── GRAPHIQUES USINE C ────────────────────────────────────────

def build_trs_chart(theme):
    trend = kpi_engine.get_trs_trend(USINE_ID, n_sessions=96)
    ts    = trend.get('timestamps',[])
    vals  = trend.get('trs_values',[])
    ma    = trend.get('ma_values',[])
    lim   = _load_limits()
    lcl   = lim.get('TRS',{}).get('lcl',0.75)
    fig   = go.Figure()
    if vals:
        fig.add_trace(go.Scatter(x=ts, y=vals, mode='lines', name='TRS',
            line=dict(color=theme['accent_blue'],width=1.2),
            fill='tozeroy', fillcolor=theme['chart_fill'],
            hovertemplate='%{x|%d %b %H:%M}<br>TRS : %{y:.3f}<extra></extra>'))
        if ma:
            fig.add_trace(go.Scatter(x=ts, y=ma, mode='lines', name='Moving avg',
                line=dict(color=theme.get('accent_green',theme['ok']),width=2),
                hovertemplate='MA : %{y:.3f}<extra></extra>'))
    fig.add_hline(y=lcl, line_dash='dot', line_color=theme['critical'], line_width=1,
                  annotation_text=f'LCL {lcl:.2f}', annotation_font_size=9,
                  annotation_font_color=theme['critical'], annotation_position='bottom right')
    fig.add_hline(y=TRS_SEUIL_ACCEPTABLE, line_dash='dot', line_color=theme['warning'], line_width=1,
                  annotation_text='Target 85%', annotation_font_size=9,
                  annotation_font_color=theme['warning'], annotation_position='top right')
    layout = _plot_layout(theme,'TRS — Real-time trend',260)
    layout['xaxis']      = _axis(theme)
    layout['yaxis']      = {**_axis(theme,'TRS'),'range':[0.55,1.05]}
    layout['showlegend'] = True
    layout['legend']     = dict(font=dict(size=9,color=theme['text_muted']),
                                bgcolor='rgba(0,0,0,0)',orientation='h',x=0,y=1.12)
    fig.update_layout(layout)
    return dcc.Graph(figure=fig, config={'displayModeBar':False})


def build_scrap_structural_chart(theme):
    buf   = store.get_buffer_as_df(USINE_ID)
    lim   = _load_limits()
    ucl_r = lim.get('taux_rebut',{}).get('ucl',0.18)
    fig   = go.Figure()
    if not buf.empty and 'type_piece' in buf.columns and 'taux_rebut' in buf.columns:
        grp = (buf.groupby('type_piece')['taux_rebut']
               .mean().reset_index().sort_values('taux_rebut',ascending=True))
        colors = [theme['critical'] if v>ucl_r else
                  theme['warning']  if v>ucl_r*0.7 else theme['ok']
                  for v in grp['taux_rebut']]
        fig.add_trace(go.Bar(
            x=grp['taux_rebut']*100,
            y=[_safe_text(p) for p in grp['type_piece']],
            orientation='h', name='Avg scrap',
            marker=dict(color=colors,opacity=0.85),
            hovertemplate='%{y} : %{x:.1f}%<extra></extra>'))
    fig.add_vline(x=ucl_r*100, line_dash='dot', line_color=theme['critical'], line_width=1.2,
                  annotation_text=f'UCL {ucl_r*100:.1f}%', annotation_font_size=9,
                  annotation_font_color=theme['critical'], annotation_position='top right')
    layout = _plot_layout(theme,'Scrap Rate by Reference — Structural instability',280)
    layout['xaxis']  = {**_axis(theme,'Scrap rate (%)'),'range':[0,25]}
    layout['yaxis']  = _axis(theme)
    layout['bargap'] = 0.3
    fig.update_layout(layout)
    return dcc.Graph(figure=fig, config={'displayModeBar':False})

# ── ONGLETS ───────────────────────────────────────────────────

def build_alerts_side(theme):
    actives   = store.get_active_alerts(USINE_ID)
    sev_color = {'CRITICAL':theme['critical'],'WARNING':theme['warning'],
                 'INFO':theme.get('accent_cyan',theme['accent_blue'])}
    items = []
    if not actives.empty:
        for _, row in actives.head(5).iterrows():
            sev   = row.get('severite','INFO')
            color = sev_color.get(sev,theme['text_muted'])
            ts    = row.get('timestamp_debut')
            ts_s  = ts.strftime('%H:%M') if hasattr(ts,'strftime') else ''
            items.append(html.Div(style={
                'borderRadius':'10px','padding':'10px 12px','marginBottom':'8px',
                'background':_rgba(color,0.07),'border':f"1px solid {_rgba(color,0.2)}",
                'borderLeft':f"3px solid {color}"}, children=[
                html.Div(style={'display':'flex','justifyContent':'space-between',
                                'alignItems':'center','marginBottom':'4px'}, children=[
                    html.Span(_safe_text(row.get('label','')),
                              style={'fontSize':'11px','fontWeight':'700','color':color}),
                    html.Span(ts_s, style={'fontSize':'10px','color':theme['text_muted']}),
                ]),
                html.Div(_safe_text(row.get('message_court','')),
                         style={'fontSize':'11px','color':theme['text_secondary'],'lineHeight':'1.4'}),
            ]))
    else:
        items.append(html.Div('No active alerts',
                              style={'color':theme['ok'],'fontSize':'12px','padding':'12px',
                                     'textAlign':'center','fontWeight':'600'}))
    return html.Div(className='panel', style={'padding':'16px'}, children=[
        html.Div('Active Alerts', className='panel-title', style={'marginBottom':'12px'}),
        html.Div(items),
    ])


def build_tab_overview(state, aggs, theme):
    return html.Div(style={'display':'grid','gridTemplateColumns':'1.6fr 1fr',
                            'gap':'16px','alignItems':'start'}, children=[
        html.Div(children=[
            html.Div(className='panel', style={'marginBottom':'14px'}, children=[
                html.Div(className='panel-head', children=[html.Div(children=[
                    html.Div('TRS Monitoring', className='panel-title'),
                    html.Div('Real-time OEE with SPC control limits', className='panel-subtitle'),
                ])]),
                html.Div(style={'padding':'0 16px 16px 16px'}, children=[build_trs_chart(theme)]),
            ]),
            html.Div(className='panel', children=[
                html.Div(className='panel-head', children=[html.Div(children=[
                    html.Div('Scrap Rate by Reference', className='panel-title'),
                    html.Div('Structural process instability — dominant pattern Usine C',
                             className='panel-subtitle'),
                ])]),
                html.Div(style={'padding':'0 16px 16px 16px'},
                         children=[build_scrap_structural_chart(theme)]),
            ]),
        ]),
        html.Div(children=[
            html.Div(className='panel', style={'padding':'16px','marginBottom':'14px'},
                     children=[build_machine_grid(theme)]),
            build_alerts_side(theme),
        ]),
    ])


def build_tab_maintenance(state, theme):
    machines     = store.get_machine_states(USINE_ID)
    machine_id   = state.get('machine_id','N/A')
    nb_pannes_7j = state.get('nb_pannes_7j',0)
    isp          = state.get('indice_stabilite_process',0.0)

    def gauge(m_id, u):
        color = theme['critical'] if u>90 else theme['warning'] if u>75 else theme['ok']
        fig = go.Figure(go.Indicator(
            mode='gauge+number', value=u,
            domain={'x':[0,1],'y':[0,1]},
            title={'text':m_id,'font':{'size':11,'color':theme['text_secondary']}},
            number={'suffix':'%','font':{'size':20,'color':color}},
            gauge={'axis':{'range':[0,100],'tickwidth':1,
                           'tickcolor':theme['text_muted'],'tickfont':{'size':8}},
                   'bar':{'color':color,'thickness':0.22},
                   'bgcolor':theme['bg_surface'],'borderwidth':0,
                   'steps':[{'range':[0,75],'color':_rgba(theme['ok'],0.08)},
                             {'range':[75,90],'color':_rgba(theme['warning'],0.12)},
                             {'range':[90,100],'color':_rgba(theme['critical'],0.16)}],
                   'threshold':{'line':{'color':theme['critical'],'width':2},
                                'thickness':0.75,'value':90}}))
        lay = _plot_layout(theme, height=180)
        lay['margin'] = dict(l=20,r=20,t=30,b=10)
        fig.update_layout(lay)
        return fig

    gauges = []
    for m_id, ms in machines.items():
        u   = ms.get('usure_pct',0.0)
        est = round((100-u)/max(u,1)*2,1) if u>0 else 0
        c   = theme['critical'] if u>90 else theme['warning'] if u>75 else theme['ok']
        gauges.append(html.Div(style={
            'borderRadius':'16px','border':f"1px solid {theme['border']}",
            'background':theme['bg_surface'],'padding':'12px','textAlign':'center'}, children=[
            dcc.Graph(figure=gauge(m_id,u), config={'displayModeBar':False}),
            html.Div(f'Est. replacement in ~{est}h',
                     style={'fontSize':'10px','color':c,'fontWeight':'600','marginTop':'4px'}),
        ]))

    def stat_card(label, val, color):
        return html.Div(style={'borderRadius':'12px','border':f"1px solid {theme['border']}",
                                'padding':'14px','background':theme['bg_surface']}, children=[
            html.Div(label, style={'fontSize':'10px','color':theme['text_muted'],
                                   'textTransform':'uppercase','fontWeight':'700'}),
            html.Div(val, style={'fontSize':'22px','fontWeight':'700','color':color,'marginTop':'6px'}),
        ])

    return html.Div(children=[
        html.Div(style={'display':'grid','gridTemplateColumns':'repeat(4,1fr)',
                        'gap':'12px','marginBottom':'16px'}, children=gauges),
        html.Div(className='panel', style={'padding':'16px'}, children=[
            html.Div('Process & Maintenance Summary', className='panel-title',
                     style={'marginBottom':'12px'}),
            html.Div(style={'display':'grid','gridTemplateColumns':'repeat(3,1fr)','gap':'10px'},
                     children=[
                stat_card('Active machine',       _safe_text(machine_id), theme['text_primary']),
                stat_card('Process Stability ISP', f'{isp:.3f}',
                          theme['critical'] if isp<0.60 else theme['warning'] if isp<0.75 else theme['ok']),
                stat_card('Failures last 7 days',  str(nb_pannes_7j),
                          theme['warning'] if nb_pannes_7j>3 else theme['ok']),
            ]),
        ]),
    ])


def build_tab_quality(state, theme):
    buf        = store.get_buffer_as_df(USINE_ID)
    taux_rebut = state.get('taux_rebut',0.0)
    pieces_reb = state.get('pieces_rebutees',0)
    type_piece = state.get('type_piece','N/A')
    equipe     = state.get('equipe','N/A')
    rc         = (theme['critical'] if taux_rebut>0.12 else
                  theme['warning']  if taux_rebut>0.08 else theme['ok'])

    def make_rows(groupby_col):
        if buf.empty or groupby_col not in buf.columns: return []
        grp = buf.groupby(groupby_col)['taux_rebut'].mean().reset_index()
        rows = []
        for _, r in grp.iterrows():
            c = (theme['critical'] if r['taux_rebut']>0.15 else
                 theme['warning']  if r['taux_rebut']>0.08 else theme['ok'])
            rows.append(html.Tr([
                html.Td(_safe_text(r[groupby_col]),
                        style={'padding':'8px 12px','fontSize':'12px',
                               'color':theme['text_primary'],'fontWeight':'600'}),
                html.Td(f"{r['taux_rebut']*100:.2f}%",
                        style={'padding':'8px 12px','fontSize':'12px',
                               'color':c,'fontWeight':'700','textAlign':'right'}),
            ], style={'borderBottom':f"1px solid {theme['border']}"}))
        return rows

    def tbl(title, col):
        rows = make_rows(col)
        return html.Div(className='panel', style={'padding':'16px'}, children=[
            html.Div(title, className='panel-title', style={'marginBottom':'12px'}),
            html.Table(style={'width':'100%','borderCollapse':'collapse'}, children=[
                html.Thead(html.Tr([
                    html.Th(col.replace('_',' ').title(),
                            style={'fontSize':'10px','color':theme['text_muted'],'textAlign':'left',
                                   'padding':'6px 12px','fontWeight':'700','textTransform':'uppercase'}),
                    html.Th('Avg Scrap',
                            style={'fontSize':'10px','color':theme['text_muted'],'textAlign':'right',
                                   'padding':'6px 12px','fontWeight':'700','textTransform':'uppercase'}),
                ])),
                html.Tbody(rows if rows else [html.Tr(html.Td(
                    'Building history...', colSpan=2,
                    style={'color':theme['text_muted'],'padding':'12px',
                           'fontSize':'11px','textAlign':'center'}))]),
            ]),
        ])

    return html.Div(children=[
        html.Div(style={'display':'grid','gridTemplateColumns':'repeat(2,1fr)',
                        'gap':'10px','marginBottom':'14px'}, children=[
            html.Div(style={'borderRadius':'12px','border':f"1px solid {theme['border']}",
                            'padding':'14px','background':theme['bg_surface']}, children=[
                html.Div('Scrap rate', style={'fontSize':'10px','color':theme['text_muted'],
                                               'textTransform':'uppercase','fontWeight':'700'}),
                html.Div(f"{taux_rebut*100:.2f}%",
                         style={'fontSize':'26px','fontWeight':'700','color':rc,'marginTop':'6px'}),
                html.Div(f'Ref : {_safe_text(type_piece)}  ·  Team : {_safe_text(equipe)}',
                         style={'fontSize':'10px','color':theme['text_muted'],'marginTop':'6px'}),
            ]),
            html.Div(style={'borderRadius':'12px','border':f"1px solid {theme['border']}",
                            'padding':'14px','background':theme['bg_surface']}, children=[
                html.Div('Parts scrapped', style={'fontSize':'10px','color':theme['text_muted'],
                                                   'textTransform':'uppercase','fontWeight':'700'}),
                html.Div(str(pieces_reb),
                         style={'fontSize':'26px','fontWeight':'700',
                                'color':theme['text_primary'],'marginTop':'6px'}),
            ]),
        ]),
        html.Div(style={'display':'grid','gridTemplateColumns':'1fr 1fr','gap':'14px'}, children=[
            tbl('Scrap by Reference', 'type_piece'),
            tbl('Scrap by Team',      'equipe'),
        ]),
    ])


def build_tab_alerts(theme):
    actives   = store.get_active_alerts(USINE_ID)
    history   = store.get_alert_history(USINE_ID, n_last=30)
    sev_color = {'CRITICAL':theme['critical'],'WARNING':theme['warning'],
                 'INFO':theme.get('accent_cyan',theme['accent_blue'])}

    def alert_row(row, is_active=True):
        sev    = row.get('severite','INFO')
        color  = sev_color.get(sev,theme['text_muted'])
        ts     = row.get('timestamp_debut')
        ts_s   = ts.strftime('%d %b %H:%M') if hasattr(ts,'strftime') else ''
        statut = row.get('statut','')
        return html.Div(style={
            'borderRadius':'12px','padding':'14px 16px','marginBottom':'8px',
            'background':_rgba(color,0.06) if is_active else theme['bg_surface'],
            'border':f"1px solid {_rgba(color,0.18) if is_active else theme['border']}",
            'borderLeft':f"3px solid {color if is_active else theme['border']}"}, children=[
            html.Div(style={'display':'flex','justifyContent':'space-between',
                            'alignItems':'flex-start','marginBottom':'6px'}, children=[
                html.Div(children=[
                    html.Span(_safe_text(row.get('label',sev)),
                              style={'fontSize':'12px','fontWeight':'700','color':color}),
                    html.Span(f" · {_safe_text(row.get('machine_id',''))}",
                              style={'fontSize':'11px','color':theme['text_muted']}),
                ]),
                html.Div(children=[
                    html.Span(ts_s, style={'fontSize':'10px','color':theme['text_muted'],
                                           'marginRight':'8px'}),
                    html.Span(_safe_text(statut), style={
                        'fontSize':'10px','fontWeight':'700',
                        'color':color if is_active else theme['ok'],
                        'padding':'2px 8px','borderRadius':'999px',
                        'border':f"1px solid {_rgba(color if is_active else theme['ok'],0.3)}",
                        'background':_rgba(color if is_active else theme['ok'],0.1)}),
                ]),
            ]),
            html.Div(_safe_text(row.get('message_court','')),
                     style={'fontSize':'11px','color':theme['text_secondary'],
                            'marginBottom':'6px','lineHeight':'1.4'}),
            html.Div(_safe_text(row.get('recommandation','')),
                     style={'fontSize':'10px','color':theme['text_muted'],'fontStyle':'italic'}),
        ])

    act = ([alert_row(r,True) for _,r in actives.iterrows()] if not actives.empty else
           [html.Div('No active alerts',style={'color':theme['ok'],'padding':'16px',
                                               'textAlign':'center','fontSize':'12px','fontWeight':'600'})])
    his = ([alert_row(r, r.get('statut')=='ACTIVE') for _,r in history.iterrows()]
           if not history.empty else
           [html.Div('No alert history yet',style={'color':theme['text_muted'],'padding':'16px',
                                                    'textAlign':'center','fontSize':'12px'})])
    return html.Div(style={'display':'grid','gridTemplateColumns':'1fr 1fr','gap':'16px'}, children=[
        html.Div(className='panel', style={'padding':'16px'}, children=[
            html.Div('Active Alerts', className='panel-title', style={'marginBottom':'12px'}),
            html.Div(act),
        ]),
        html.Div(className='panel', style={'padding':'16px'}, children=[
            html.Div('Alert History (last 30)', className='panel-title', style={'marginBottom':'12px'}),
            html.Div(his, style={'maxHeight':'500px','overflowY':'auto'}),
        ]),
    ])

# ── TAB BAR ───────────────────────────────────────────────────

def _build_tab_bar(active_tab: str, theme: dict) -> html.Div:
    def btn(label, tab_id, btn_id):
        active = active_tab == tab_id
        return html.Button(label, id=btn_id, n_clicks=0, style={
            'background': _rgba(theme['accent_blue'],0.12) if active else 'transparent',
            'border': f"1px solid {_rgba(theme['accent_blue'],0.25) if active else theme['border']}",
            'color': theme['accent_blue'] if active else theme['text_muted'],
            'borderRadius':'10px','padding':'6px 16px','fontSize':'11px',
            'fontWeight':'700','cursor':'pointer','fontFamily':'Inter, sans-serif',
        })
    return html.Div(style={
        'display':'flex','gap':'8px','padding':'10px 22px',
        'borderBottom':f"1px solid {theme['border']}",
        'background':theme.get('bg_sidebar',theme['bg_card']),
        'position':'sticky','top':'57px','zIndex':'15',
    }, children=[
        btn('Overview',    'overview',    'tab-btn-overview-C'),
        btn('Maintenance', 'maintenance', 'tab-btn-maintenance-C'),
        btn('Quality',     'quality',     'tab-btn-quality-C'),
        btn('Alerts',      'alerts',      'tab-btn-alerts-C'),
    ])

# ── LAYOUT ────────────────────────────────────────────────────

_init_theme = _soft_theme(DEFAULT_THEME_MODE)

app.layout = html.Div(
    id='root-C',
    style={'minHeight':'100vh'},
    children=[
        dcc.Interval(id='interval-C', interval=1000, n_intervals=0),
        dcc.Store(id='tab-store-C', data='overview'),
        html.Div(id='page-content-C'),
        html.Div(
            id='tab-bar-container-C',
            children=_build_tab_bar('overview', _init_theme),  # ← initialisé avec le contenu réel
        ),
    ]
)

# ── CALLBACKS ─────────────────────────────────────────────────

@app.callback(
    Output('tab-store-C', 'data'),
    Input('tab-btn-overview-C',    'n_clicks'),
    Input('tab-btn-maintenance-C', 'n_clicks'),
    Input('tab-btn-quality-C',     'n_clicks'),
    Input('tab-btn-alerts-C',      'n_clicks'),
    prevent_initial_call=True,
)
def switch_tab_C(n1, n2, n3, n4):
    mapping = {
        'tab-btn-overview-C':    'overview',
        'tab-btn-maintenance-C': 'maintenance',
        'tab-btn-quality-C':     'quality',
        'tab-btn-alerts-C':      'alerts',
    }
    return mapping.get(ctx.triggered_id, 'overview')


@app.callback(
    Output('tab-bar-container-C', 'children'),
    Input('tab-store-C', 'data'),
)
def update_tab_bar_C(active_tab):
    return _build_tab_bar(active_tab or 'overview', _soft_theme(DEFAULT_THEME_MODE))


@app.callback(
    Output('page-content-C', 'children'),
    Input('interval-C', 'n_intervals'),
    State('tab-store-C', 'data'),          # ← State pas Input
)
def update_page_C(n, active_tab):
    ensure_simulator_started()
    theme      = _soft_theme(DEFAULT_THEME_MODE)
    state      = store.get_current_state(USINE_ID)
    aggs       = store.get_aggregations(USINE_ID)
    all_alts   = store.get_active_alerts(USINE_ID)
    persistent = _get_persistent_alerts(all_alts)

    ts_str = 'N/A'
    sim    = store.get_sim_state(USINE_ID)
    ts     = sim.get('timestamp_simule')
    if ts and hasattr(ts,'strftime'):
        ts_str = ts.strftime('%d %b %Y · %H:%M')

    active_tab = active_tab or 'overview'
    if   active_tab == 'maintenance': tab_content = build_tab_maintenance(state, theme)
    elif active_tab == 'quality':     tab_content = build_tab_quality(state, theme)
    elif active_tab == 'alerts':      tab_content = build_tab_alerts(theme)
    else:                             tab_content = build_tab_overview(state, aggs, theme)

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
                    html.Div(f"MECHA Monitoring System · {SITE_LABEL} · Port {PORT}",
                             className='footer-note'),
                ]),
            ]),
        ])],
    )


if __name__ == '__main__':
    ensure_simulator_started()
    app.run(debug=False, port=PORT, host='0.0.0.0')
