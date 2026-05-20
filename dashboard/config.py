# ============================================================
# config.py — Configuration centrale du système de monitoring MECHA
# ============================================================

from pathlib import Path

# ── Racine du projet ──────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent

# ── Chemins vers les données Gold ─────────────────────────────
GOLD_PATHS = {
    'Usine_A': ROOT / 'data' / 'gold' / 'usine_A.parquet',
    'Usine_B': ROOT / 'data' / 'gold' / 'usine_B.parquet',
    'Usine_C': ROOT / 'data' / 'gold' / 'usine_C.parquet',
}

LIMITS_PATHS = {
    'Usine_A': ROOT / 'data' / 'gold' / 'limites_usine_A.json',
    'Usine_B': ROOT / 'data' / 'gold' / 'limites_usine_B.json',
    'Usine_C': ROOT / 'data' / 'gold' / 'limites_usine_C.json',
}

# ── Identité des usines ───────────────────────────────────────
USINES = ['Usine_A', 'Usine_B', 'Usine_C']

USINE_LABELS = {
    'Usine_A': 'Usine A — Lyon',
    'Usine_B': 'Usine B — Bordeaux',
    'Usine_C': 'Usine C — Toulouse',
}

USINE_PORTS = {
    'Usine_A': 8051,
    'Usine_B': 8052,
    'Usine_C': 8053,
}

MACHINES = ['M01', 'M02', 'M03', 'M04']

# ── Problème dominant par usine ──────────────────────────────
USINE_DOMINANT_PROBLEM = {
    'Usine_A': 'Usure outil progressive',
    'Usine_B': 'Pannes thermiques clustérisées',
    'Usine_C': 'Instabilité process structurelle',
}

# ── Simulation temps réel ─────────────────────────────────────
SIMULATION_INTERVAL_S  = 10
SESSION_DURATION_MIN   = 10
BUFFER_SIZE_SESSIONS   = 1152

# ── Seuils industriels globaux ────────────────────────────────
TRS_SEUIL_ACCEPTABLE   = 0.85
TRS_SEUIL_CRITIQUE     = 0.75
REBUT_SEUIL_ACCEPTABLE = 0.05
USURE_SEUIL_WARNING    = 0.75
USURE_SEUIL_CRITIQUE   = 0.90

# ── Règles d'alerte ───────────────────────────────────────────
ALERT_RULES = {

    'derive_qualite': {
        'kpi'         : 'taux_rebut',
        'condition'   : 'above',
        'seuil_src'   : 'json',
        'seuil_key'   : 'taux_rebut.ucl',
        'severite'    : 'WARNING',
        'cooldown_s'  : 300,
        'persistence' : 3,
        'label'       : 'Dérive Qualité',
        'message'     : (
            "Le taux de rebut dépasse la limite de contrôle supérieure. "
            "Risque de production non conforme. "
            "Vérifier les paramètres process et l'état de l'outillage."
        ),
    },

    'machine_arretee': {
        'kpi'         : 'panne_machine',
        'condition'   : 'equals',
        'seuil_src'   : 'fixed',
        'seuil_value' : 1,
        'severite'    : 'CRITICAL',
        'cooldown_s'  : 0,
        'persistence' : 1,
        'label'       : 'Arrêt Machine',
        'message'     : (
            "Machine à l'arrêt détectée. "
            "Production interrompue. "
            "Intervention maintenance requise immédiatement."
        ),
    },

    'derive_cycle': {
        'kpi'         : 'derive_cycle_pct',
        'condition'   : 'above',
        'seuil_src'   : 'fixed',
        'seuil_value' : 20.0,
        'severite'    : 'WARNING',
        'cooldown_s'  : 600,
        'persistence' : 5,
        'label'       : 'Dérive Temps de Cycle',
        'message'     : (
            "Le temps de cycle dépasse de plus de 20% la valeur nominale. "
            "Cadence de production dégradée. "
            "Vérifier l'usure outil et les conditions d'usinage."
        ),
    },

    'rupture_appro': {
        'kpi'         : 'rupture_appro',
        'condition'   : 'equals',
        'seuil_src'   : 'fixed',
        'seuil_value' : 1,
        'severite'    : 'CRITICAL',
        'cooldown_s'  : 0,
        'persistence' : 1,
        'label'       : 'Rupture Approvisionnement',
        'message'     : (
            "Rupture d'approvisionnement détectée. "
            "Production arrêtée faute de matière. "
            "Alerter le responsable supply chain immédiatement."
        ),
    },

    'usure_critique': {
        'kpi'         : 'usure_cumulee_pct',
        'condition'   : 'above',
        'seuil_src'   : 'fixed',
        'seuil_value' : USURE_SEUIL_CRITIQUE * 100,
        'severite'    : 'CRITICAL',
        'cooldown_s'  : 120,
        'persistence' : 2,
        'label'       : 'Usure Outil Critique',
        'message'     : (
            "L'usure outil dépasse 90% de la durée de vie nominale. "
            "Risque de panne par usure outil imminent. "
            "Planifier le remplacement avant la prochaine session."
        ),
    },

    'usure_warning': {
        'kpi'         : 'usure_cumulee_pct',
        'condition'   : 'above',
        'seuil_src'   : 'fixed',
        'seuil_value' : USURE_SEUIL_WARNING * 100,
        'severite'    : 'INFO',
        'cooldown_s'  : 600,
        'persistence' : 1,
        'label'       : 'Usure Outil Élevée',
        'message'     : (
            "L'usure outil approche du seuil de remplacement. "
            "Anticiper l'intervention pour éviter un arrêt non planifié."
        ),
    },

    'derive_thermique': {
        'kpi'         : 'temp_process_delta',
        'condition'   : 'below',
        'seuil_src'   : 'json',
        'seuil_key'   : 'temp_process_delta.lcl',
        'severite'    : 'WARNING',
        'cooldown_s'  : 300,
        'persistence' : 3,
        'label'       : 'Dérive Thermique',
        'message'     : (
            "Le delta thermique process/air descend sous la limite critique. "
            "Risque de panne par dissipation thermique insuffisante (HDF). "
            "Vérifier le système de refroidissement."
        ),
    },

    'trs_critique': {
        'kpi'         : 'TRS',
        'condition'   : 'below',
        'seuil_src'   : 'fixed',
        'seuil_value' : TRS_SEUIL_CRITIQUE,
        'severite'    : 'CRITICAL',
        'cooldown_s'  : 300,
        'persistence' : 5,
        'label'       : 'TRS Critique',
        'message'     : (
            "Le TRS est descendu sous le seuil critique de 75%. "
            "Performance industrielle inacceptable. "
            "Analyse root-cause requise immédiatement."
        ),
    },

}

# ── Thème Dark ────────────────────────────────────────────────
DARK_THEME = {
    'bg_primary'     : '#071018',
    'bg_card'        : '#0f1822',
    'bg_surface'     : '#111c28',
    'border'         : 'rgba(255,255,255,0.07)',
    'text_primary'   : '#ecf2f8',
    'text_secondary' : '#b0bcc9',
    'text_muted'     : '#7d8a98',
    'accent_blue'    : '#5b7fa3',
    'accent_purple'  : '#6b7394',
    'ok'             : '#4d8c6f',
    'warning'        : '#b68a52',
    'critical'       : '#b85c5c',
    'info'           : '#5b8f95',
    'chart_grid'     : '#182433',
    'chart_line'     : '#5b7fa3',
    'chart_fill'     : 'rgba(91,127,163,0.10)',
    'ucl_color'      : '#b85c5c',
    'lcl_color'      : '#b85c5c',
    'uwl_color'      : '#b68a52',
    'paper_bgcolor'  : '#0f1822',
    'plot_bgcolor'   : '#0f1822',
    'font_color'     : '#b0bcc9',
    'mode'           : 'dark',
}

# ── Thème Light ───────────────────────────────────────────────
LIGHT_THEME = {
    'bg_primary'     : '#f4f6f8',
    'bg_card'        : '#ffffff',
    'bg_surface'     : '#f8fafc',
    'border'         : 'rgba(16,24,40,0.08)',
    'text_primary'   : '#101828',
    'text_secondary' : '#475467',
    'text_muted'     : '#667085',
    'accent_blue'    : '#315ea8',
    'accent_purple'  : '#4f5f9f',
    'ok'             : '#2f855a',
    'warning'        : '#b7791f',
    'critical'       : '#b54747',
    'info'           : '#3f7f8f',
    'chart_grid'     : '#e5eaf0',
    'chart_line'     : '#315ea8',
    'chart_fill'     : 'rgba(49,94,168,0.10)',
    'ucl_color'      : '#b54747',
    'lcl_color'      : '#b54747',
    'uwl_color'      : '#b7791f',
    'paper_bgcolor'  : '#ffffff',
    'plot_bgcolor'   : '#f8fafc',
    'font_color'     : '#475467',
    'mode'           : 'light',
}

# ── Sélecteur de thème ────────────────────────────────────────
def get_theme(mode: str = 'dark') -> dict:
    return DARK_THEME if mode == 'dark' else LIGHT_THEME

# ── Typographie ───────────────────────────────────────────────
FONT_FAMILY   = 'Inter, -apple-system, BlinkMacSystemFont, sans-serif'
FONT_SIZE_KPI = '32px'
FONT_SIZE_LBL = '11px'
FONT_SIZE_TXT = '12px'
FONT_SIZE_ALT = '12px'
FONT_SIZE_TS  = '10px'

# ── Layout général ────────────────────────────────────────────
CARD_PADDING    = '16px 20px'
CARD_RADIUS     = '10px'
CARD_SHADOW_DK  = '0 2px 12px rgba(0,0,0,0.4)'
CARD_SHADOW_LT  = '0 2px 8px rgba(0,0,0,0.08)'

# ── Labels des KPIs pour l'affichage ─────────────────────────
KPI_LABELS = {
    'TRS'                  : 'TRS',
    'disponibilite'        : 'Disponibilité',
    'performance'          : 'Performance',
    'qualite'              : 'Qualité',
    'taux_rebut'           : 'Taux de Rebut',
    'temps_cycle_min'      : 'Temps de Cycle',
    'temp_process_delta'   : 'Delta Thermique',
    'usure_cumulee_pct'    : 'Usure Outil',
    'consommation_kwh'     : 'Consommation',
    'derive_cycle_pct'     : 'Dérive Cycle',
}

KPI_UNITS = {
    'TRS'                  : '%',
    'disponibilite'        : '%',
    'performance'          : '%',
    'qualite'              : '%',
    'taux_rebut'           : '%',
    'temps_cycle_min'      : 'min',
    'temp_process_delta'   : 'K',
    'usure_cumulee_pct'    : '%',
    'consommation_kwh'     : 'kWh',
    'derive_cycle_pct'     : '%',
}

KPI_PERCENT = {
    'TRS', 'disponibilite', 'performance',
    'qualite', 'taux_rebut'
}

print("✓ config.py chargé — système de monitoring MECHA initialisé")