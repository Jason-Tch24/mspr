# =============================================================================
# ml_poc_mecha_rul_thermique.py
# Projet MECHA — PoC Intelligence Artificielle
# MSPR TPRE831 / TPRE841
#
# Ce script implémente deux cas d'usage de machine learning industriel :
#   - Usine A : Prédiction de la durée de vie résiduelle (RUL) de l'outil de coupe
#   - Usine B : Classification du risque thermique (Normal / Risque / Critique)
#
# Les modèles sont entraînés sur les datasets Gold déjà existants.
# Ce script constitue un PoC illustrant la faisabilité d'une couche IA
# prédictive intégrée dans l'architecture Medallion de MECHA.
#
# DÉPENDANCES MINIMALES :
#   pip install pandas numpy matplotlib scikit-learn pyarrow
#
# STRUCTURE :
#   data/gold/usine_A.parquet
#   data/gold/usine_B.parquet
#   notebooks/ml_poc_mecha_rul_thermique.py  <-- ce fichier
#
# OUTPUTS :
#   ml_usine_A_rul_reel_vs_predit.png
#   ml_usine_A_importances.png
#   ml_usine_B_confusion_matrix.png
#   ml_usine_B_importances.png
# =============================================================================

import sys
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.colors import LinearSegmentedColormap

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    classification_report,
    confusion_matrix,
    balanced_accuracy_score,
)
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

# =============================================================================
# CONFIGURATION GLOBALE
# =============================================================================

# Style académique sobre — fond blanc, propre, adapté rapport PDF
plt.rcParams.update({
    'figure.facecolor'  : 'white',
    'axes.facecolor'    : 'white',
    'axes.edgecolor'    : '#444444',
    'axes.linewidth'    : 1.0,
    'axes.grid'         : True,
    'grid.color'        : '#dddddd',
    'grid.linewidth'    : 0.7,
    'font.family'       : 'DejaVu Sans',
    'font.size'         : 11,
    'axes.titlesize'    : 13,
    'axes.labelsize'    : 11,
    'xtick.labelsize'   : 10,
    'ytick.labelsize'   : 10,
    'legend.fontsize'   : 10,
    'figure.dpi'        : 150,
    'savefig.dpi'       : 200,
    'savefig.bbox'      : 'tight',
    'savefig.facecolor' : 'white',
})

# Couleurs industrielles sobres cohérentes avec le rapport
COLOR_PRIMARY   = '#1f497d'   # bleu industriel
COLOR_SECONDARY = '#c0392b'   # rouge alerte
COLOR_OK        = '#27ae60'   # vert OK
COLOR_WARN      = '#e67e22'   # orange warning
COLOR_MUTED     = '#7f8c8d'   # gris neutre

# =============================================================================
# CHEMINS
# =============================================================================

# Ce script est dans notebooks/ — remonter d'un niveau pour accéder à data/
SCRIPT_DIR  = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_GOLD   = PROJECT_DIR / 'data' / 'gold'
OUTPUT_DIR  = SCRIPT_DIR  # les PNG sont générés à côté du script

PATH_A = DATA_GOLD / 'usine_A.parquet'
PATH_B = DATA_GOLD / 'usine_B.parquet'

print("=" * 65)
print("  MECHA — PoC Machine Learning · RUL & Risque Thermique")
print("=" * 65)
print(f"  Répertoire projet  : {PROJECT_DIR}")
print(f"  Données Gold       : {DATA_GOLD}")
print(f"  Usine A            : {PATH_A}")
print(f"  Usine B            : {PATH_B}")
print(f"  Outputs PNG        : {OUTPUT_DIR}")
print("=" * 65)

# =============================================================================
# UTILITAIRES
# =============================================================================

def check_file(path: Path) -> None:
    """Vérifie l'existence d'un fichier et arrête le script si absent."""
    if not path.exists():
        print(f"\n[ERREUR] Fichier introuvable : {path}")
        print("  Vérifiez que le pipeline Gold a bien été exécuté.")
        sys.exit(1)
    print(f"  [OK] Fichier trouvé : {path.name}  ({path.stat().st_size / 1024:.0f} Ko)")


def check_columns(df: pd.DataFrame, required: list, context: str) -> None:
    """Vérifie la présence de colonnes obligatoires dans un DataFrame."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"\n[ERREUR] Colonnes manquantes dans {context} :")
        for col in missing:
            print(f"  - {col}")
        print(f"\n  Colonnes disponibles dans {context} :")
        for col in df.columns.tolist():
            print(f"    {col}")
        sys.exit(1)


def temporal_split(df: pd.DataFrame, train_ratio=0.70, val_ratio=0.15):
    """
    Split temporel strict — conserve l'ordre chronologique.
    Retourne (train, val, test) sans mélange aléatoire.
    Le split temporel est indispensable pour les séries temporelles
    industrielles : un split aléatoire introduirait du data leakage.
    """
    n = len(df)
    i_train = int(n * train_ratio)
    i_val   = int(n * (train_ratio + val_ratio))
    return df.iloc[:i_train], df.iloc[i_train:i_val], df.iloc[i_val:]


def save_figure(fig: plt.Figure, filename: str) -> Path:
    """Sauvegarde une figure et affiche le chemin."""
    path = OUTPUT_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    print(f"  [PNG] {path.name}")
    return path


# =============================================================================
# CHARGEMENT DES DONNÉES
# =============================================================================

print("\n── Chargement des données Gold ──────────────────────────────")
check_file(PATH_A)
check_file(PATH_B)

df_A = pd.read_parquet(PATH_A)
df_B = pd.read_parquet(PATH_B)

print(f"\n  Usine A : {len(df_A):,} sessions · {len(df_A.columns)} colonnes")
print(f"  Usine B : {len(df_B):,} sessions · {len(df_B.columns)} colonnes")

print("\n  Colonnes Usine A :")
print("  " + ", ".join(df_A.columns.tolist()))
print("\n  Colonnes Usine B :")
print("  " + ", ".join(df_B.columns.tolist()))

# =============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  USINE A — PRÉDICTION DE LA DURÉE DE VIE RÉSIDUELLE (RUL)
# ─────────────────────────────────────────────────────────────────────────────
# =============================================================================

print("\n" + "=" * 65)
print("  USINE A — Prédiction RUL (Remaining Useful Life)")
print("=" * 65)

# ── Validation des colonnes obligatoires ──────────────────────────────────────
COLS_A_REQUIRED = ['usure_cumulee_pct', 'remplacement_outil', 'TRS']
check_columns(df_A, COLS_A_REQUIRED, 'Usine A')

# ── Colonnes optionnelles avec fallback ───────────────────────────────────────
def col_or_zero(df, col):
    """Retourne la colonne si présente, sinon une série de zéros."""
    if col in df.columns:
        return df[col]
    print(f"  [INFO] Colonne '{col}' absente → remplacée par 0 pour les features")
    return pd.Series(0.0, index=df.index)

# ── Construction de la cible RUL ──────────────────────────────────────────────
# Logique :
#   Pour chaque session, la cible est le nombre de sessions restantes
#   avant le prochain événement remplacement_outil == 1.
#   Si aucun remplacement n'est prévu dans les sessions suivantes (fin du dataset),
#   on utilise la distance jusqu'à la fin du cycle en cours.
#
#   Exemple : si un remplacement survient à la session 240, alors :
#     session 239 → RUL = 1
#     session 238 → RUL = 2
#     session 237 → RUL = 3  etc.
#
#   Cette cible est strictement temporelle et ne doit jamais être construite
#   avec un split aléatoire (risque de regarder dans le futur = data leakage).

print("\n── Construction de la cible RUL ─────────────────────────────")

df_A = df_A.reset_index(drop=True).copy()

# S'assurer que remplacement_outil est numérique
df_A['remplacement_outil'] = pd.to_numeric(df_A['remplacement_outil'], errors='coerce').fillna(0)

# Construction de la RUL par backward filling depuis chaque remplacement
rul_values = np.zeros(len(df_A), dtype=float)

# Identifier les index de remplacement
remplacement_idx = df_A.index[df_A['remplacement_outil'] == 1].tolist()

if len(remplacement_idx) == 0:
    print("[ERREUR] Aucun événement remplacement_outil trouvé dans Usine A.")
    print("  Vérifiez la colonne remplacement_outil dans le dataset Gold.")
    sys.exit(1)

print(f"  Événements de remplacement détectés : {len(remplacement_idx)}")

# Pour chaque session, calculer la distance jusqu'au prochain remplacement
# On travaille de droite à gauche pour chaque bloc inter-remplacement
prev_remplacement = None
for i in reversed(range(len(df_A))):
    if df_A.loc[i, 'remplacement_outil'] == 1:
        rul_values[i] = 0
        prev_remplacement = i
    elif prev_remplacement is not None:
        rul_values[i] = prev_remplacement - i
    else:
        # Après le dernier remplacement (fin de dataset) : RUL inconnue
        # On extrapole depuis la fin — valeur croissante vers la gauche
        rul_values[i] = 0  # sera masqué dans les features

df_A['rul_target'] = rul_values

# Supprimer les sessions sans cible valide (après le dernier remplacement)
# et les sessions avec RUL == 0 qui sont les remplacements eux-mêmes
df_A_ml = df_A[df_A['rul_target'] > 0].copy()
print(f"  Sessions avec cible RUL > 0 : {len(df_A_ml):,} / {len(df_A):,}")
print(f"  RUL min : {df_A_ml['rul_target'].min():.0f}  max : {df_A_ml['rul_target'].max():.0f}  "
      f"mean : {df_A_ml['rul_target'].mean():.1f} sessions")

# ── Feature engineering Usine A ───────────────────────────────────────────────
print("\n── Feature engineering Usine A ──────────────────────────────")

df_A_ml = df_A_ml.copy()

# Features directes
FEAT_A_BASE = ['usure_cumulee_pct', 'TRS']
FEAT_A_OPT  = [
    'temps_cycle_min', 'derive_cycle_pct', 'disponibilite',
    'performance', 'qualite', 'consommation_kwh',
    'vitesse_rotation_rpm', 'couple_nm', 'taux_rebut',
]

# Lags de l'usure (dépendance temporelle)
for lag in [1, 2, 3, 5]:
    df_A_ml[f'usure_lag_{lag}'] = df_A_ml['usure_cumulee_pct'].shift(lag)

# Rolling features de l'usure
for w in [5, 10, 20]:
    df_A_ml[f'usure_roll_mean_{w}'] = (
        df_A_ml['usure_cumulee_pct'].rolling(w, min_periods=1).mean()
    )
    df_A_ml[f'usure_roll_std_{w}'] = (
        df_A_ml['usure_cumulee_pct'].rolling(w, min_periods=1).std().fillna(0)
    )

# Dérivée de l'usure (taux de dégradation)
df_A_ml['usure_delta'] = df_A_ml['usure_cumulee_pct'].diff().fillna(0)

# Construire la liste finale des features disponibles
features_A = FEAT_A_BASE.copy()
for col in FEAT_A_OPT:
    if col in df_A_ml.columns:
        features_A.append(col)
    else:
        print(f"  [INFO] Feature optionnelle '{col}' absente — ignorée")

lag_and_roll_cols = [c for c in df_A_ml.columns if c.startswith('usure_lag_')
                     or c.startswith('usure_roll_')
                     or c == 'usure_delta']
features_A += lag_and_roll_cols

# Supprimer les lignes avec NaN sur les features (dues aux lags)
df_A_ml = df_A_ml.dropna(subset=features_A + ['rul_target'])
print(f"  Features utilisées ({len(features_A)}) : {features_A}")
print(f"  Sessions après nettoyage NaN : {len(df_A_ml):,}")

# ── Split temporel Usine A ────────────────────────────────────────────────────
print("\n── Split temporel Usine A (70 / 15 / 15) ───────────────────")

train_A, val_A, test_A = temporal_split(df_A_ml)
print(f"  Train : {len(train_A):,} sessions")
print(f"  Val   : {len(val_A):,} sessions")
print(f"  Test  : {len(test_A):,} sessions")

X_train_A = train_A[features_A]
y_train_A = train_A['rul_target']
X_val_A   = val_A[features_A]
y_val_A   = val_A['rul_target']
X_test_A  = test_A[features_A]
y_test_A  = test_A['rul_target']

# ── Modèle Usine A ────────────────────────────────────────────────────────────
print("\n── Entraînement Random Forest Regressor (Usine A) ───────────")

rf_A = RandomForestRegressor(
    n_estimators=200,
    max_depth=15,
    min_samples_leaf=5,
    min_samples_split=10,
    random_state=42,
    n_jobs=-1,
)
rf_A.fit(X_train_A, y_train_A)
print("  Modèle entraîné.")

# Métriques sur le jeu de test
y_pred_A = rf_A.predict(X_test_A)
mae_A    = mean_absolute_error(y_test_A, y_pred_A)
rmse_A   = np.sqrt(mean_squared_error(y_test_A, y_pred_A))
r2_A     = r2_score(y_test_A, y_pred_A)

# Métriques sur le jeu de validation
y_pred_val_A = rf_A.predict(X_val_A)
mae_val_A    = mean_absolute_error(y_val_A, y_pred_val_A)
r2_val_A     = r2_score(y_val_A, y_pred_val_A)

print(f"\n  ── Métriques Usine A ──────────────────────────")
print(f"  Validation  → MAE : {mae_val_A:.2f} sessions  R² : {r2_val_A:.3f}")
print(f"  Test        → MAE : {mae_A:.2f} sessions  RMSE : {rmse_A:.2f}  R² : {r2_A:.3f}")

# ── Graphique 1 Usine A — Réel vs Prédit ──────────────────────────────────────
print("\n── Graphiques Usine A ───────────────────────────────────────")
generated_files = []

fig, ax = plt.subplots(figsize=(10, 5))

idx_plot = np.arange(len(y_test_A))
ax.plot(idx_plot, y_test_A.values, color=COLOR_PRIMARY,
        linewidth=1.2, label='RUL réelle', alpha=0.85)
ax.plot(idx_plot, y_pred_A, color=COLOR_SECONDARY,
        linewidth=1.0, linestyle='--', label='RUL prédite', alpha=0.85)

ax.set_title(
    f'Usine A — RUL réelle vs prédite (jeu de test)\n'
    f'MAE = {mae_A:.1f} sessions · RMSE = {rmse_A:.1f} · R² = {r2_A:.3f}',
    pad=12
)
ax.set_xlabel('Index session (jeu de test, ordre chronologique)')
ax.set_ylabel('Durée de vie résiduelle (sessions)')
ax.legend(loc='upper right')
ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

fig.tight_layout()
generated_files.append(save_figure(fig, 'ml_usine_A_rul_reel_vs_predit.png'))

# ── Graphique 2 Usine A — Scatter réel vs prédit ──────────────────────────────
fig, ax = plt.subplots(figsize=(6, 6))

ax.scatter(y_test_A.values, y_pred_A,
           alpha=0.35, s=14, color=COLOR_PRIMARY, edgecolors='none')
lim = max(y_test_A.max(), y_pred_A.max()) * 1.05
ax.plot([0, lim], [0, lim], color=COLOR_MUTED, linewidth=1.2,
        linestyle='--', label='Prédiction parfaite')

ax.set_title(
    f'Usine A — Scatter RUL réelle vs prédite\nR² = {r2_A:.3f}',
    pad=12
)
ax.set_xlabel('RUL réelle (sessions)')
ax.set_ylabel('RUL prédite (sessions)')
ax.legend()
ax.set_xlim(left=0)
ax.set_ylim(bottom=0)

fig.tight_layout()
generated_files.append(save_figure(fig, 'ml_usine_A_rul_scatter.png'))

# ── Graphique 3 Usine A — Importance des features ─────────────────────────────
importances_A = pd.Series(rf_A.feature_importances_, index=features_A)
importances_A = importances_A.sort_values(ascending=True).tail(15)

fig, ax = plt.subplots(figsize=(9, 5))

bars = ax.barh(importances_A.index, importances_A.values,
               color=COLOR_PRIMARY, alpha=0.80, edgecolor='white', height=0.65)
ax.set_title('Usine A — Importance des features (Random Forest Regressor)', pad=12)
ax.set_xlabel('Importance relative')
ax.set_xlim(right=importances_A.values.max() * 1.15)

# Valeurs en bout de barre
for bar, val in zip(bars, importances_A.values):
    ax.text(val + importances_A.values.max() * 0.01, bar.get_y() + bar.get_height() / 2,
            f'{val:.3f}', va='center', ha='left', fontsize=9, color='#333333')

fig.tight_layout()
generated_files.append(save_figure(fig, 'ml_usine_A_importances.png'))

# =============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  USINE B — CLASSIFICATION DU RISQUE THERMIQUE (v2)
#  Améliorations vs v1 :
#    - Horizon CRITIQUE réduit à 3 sessions (→ plus de samples Critique)
#    - Features enrichies : temp_process_c, usure_cumulee_pct, couple_nm,
#      vitesse_rotation_rpm, indice_stabilite_process, panne_usure_outil
#    - SMOTE sur le jeu d'entraînement pour rééquilibrer les classes
#    - XGBoost Classifier (meilleure gestion du déséquilibre de classes)
# ─────────────────────────────────────────────────────────────────────────────
# =============================================================================

print("\n" + "=" * 65)
print("  USINE B — Classification du risque thermique (v2)")
print("=" * 65)

# ── Validation des colonnes obligatoires ──────────────────────────────────────
COLS_B_REQUIRED = ['temp_process_delta', 'TRS']
check_columns(df_B, COLS_B_REQUIRED, 'Usine B')

# ── Colonne de panne thermique avec fallback ───────────────────────────────────
if 'panne_thermique' in df_B.columns:
    panne_col = 'panne_thermique'
    print(f"  Colonne de panne utilisée : '{panne_col}'")
elif 'panne_machine' in df_B.columns:
    panne_col = 'panne_machine'
    print(f"  [FALLBACK] 'panne_thermique' absente → utilisation de '{panne_col}'")
else:
    print("[ERREUR] Aucune colonne de panne trouvée (panne_thermique ou panne_machine).")
    sys.exit(1)

df_B = df_B.reset_index(drop=True).copy()
df_B[panne_col] = pd.to_numeric(df_B[panne_col], errors='coerce').fillna(0)

# ── Construction des labels de risque thermique ───────────────────────────────
# Logique forward-looking :
#   Pour chaque session t, on regarde les sessions futures :
#     - si une panne survient dans les 3 prochaines sessions (1h30 simulées) → CRITIQUE (2)
#     - si une panne survient dans les 4 à 48 sessions suivantes (1h30–24h)  → RISQUE   (1)
#     - sinon                                                                 → NORMAL   (0)
#
# HORIZON_CRITIQUE réduit à 3 (vs 6 en v1) pour augmenter les samples Critique.
# Priorité métier : minimiser les faux négatifs CRITIQUE.

print("\n── Construction des labels de risque thermique ──────────────")

HORIZON_CRITIQUE = 3    # sessions imminentes → CRITIQUE (réduit de 6 à 3)
HORIZON_RISQUE   = 48   # sessions à risque   → RISQUE

panne_arr = df_B[panne_col].values
n_B       = len(df_B)
labels_B  = np.zeros(n_B, dtype=int)

for i in range(n_B):
    fin_crit = min(i + HORIZON_CRITIQUE + 1, n_B)
    if panne_arr[i + 1 : fin_crit].sum() > 0:
        labels_B[i] = 2
        continue
    fin_risq = min(i + HORIZON_RISQUE + 1, n_B)
    if panne_arr[i + HORIZON_CRITIQUE + 1 : fin_risq].sum() > 0:
        labels_B[i] = 1

df_B['risque_label'] = labels_B

counts_B   = pd.Series(labels_B).value_counts().sort_index()
label_names = {0: 'Normal', 1: 'Risque', 2: 'Critique'}
print(f"  Distribution des classes :")
for k, v in counts_B.items():
    print(f"    {k} ({label_names[k]}) : {v:,} sessions  ({v/n_B*100:.1f}%)")

# ── Feature engineering Usine B (enrichi) ─────────────────────────────────────
print("\n── Feature engineering Usine B (enrichi) ────────────────────")

df_B_ml = df_B.copy()

# Base : signaux thermiques + performance globale
FEAT_B_BASE = ['temp_process_delta', 'TRS']

# Optionnelles v1 (déjà présentes)
FEAT_B_OPT_V1 = [
    'taux_rebut', 'disponibilite', 'performance',
    'consommation_kwh', 'temps_cycle_min', 'derive_cycle_pct',
    'nb_pannes_7j',
]

# Nouvelles features v2 : signaux physiques liés à la thermique
FEAT_B_OPT_V2 = [
    'temp_process_c',          # température absolue process (plus stable que delta)
    'usure_cumulee_pct',       # usure outil → friction → chaleur
    'couple_nm',               # couple élevé → frottement → montée thermique
    'vitesse_rotation_rpm',    # vitesse → dissipation thermique
    'indice_stabilite_process',# instabilité = précurseur de dérive thermique
    'panne_usure_outil',       # panne par usure outil corrélée avec thermique
]

# Lags et rolling sur le delta thermique
for lag in [1, 2, 3, 5]:
    df_B_ml[f'delta_lag_{lag}'] = df_B_ml['temp_process_delta'].shift(lag)

for w in [5, 10, 20]:
    df_B_ml[f'delta_roll_mean_{w}'] = (
        df_B_ml['temp_process_delta'].rolling(w, min_periods=1).mean()
    )
    df_B_ml[f'delta_roll_std_{w}'] = (
        df_B_ml['temp_process_delta'].rolling(w, min_periods=1).std().fillna(0)
    )

df_B_ml['delta_deriv']  = df_B_ml['temp_process_delta'].diff().fillna(0)
df_B_ml['delta_deriv2'] = df_B_ml['delta_deriv'].diff().fillna(0)

# Rolling sur temp_process_c (signal absolu)
if 'temp_process_c' in df_B_ml.columns:
    for w in [5, 10]:
        df_B_ml[f'temp_c_roll_mean_{w}'] = (
            df_B_ml['temp_process_c'].rolling(w, min_periods=1).mean()
        )
    df_B_ml['temp_c_deriv'] = df_B_ml['temp_process_c'].diff().fillna(0)

# Rolling sur usure
if 'usure_cumulee_pct' in df_B_ml.columns:
    df_B_ml['usure_roll_mean_10'] = (
        df_B_ml['usure_cumulee_pct'].rolling(10, min_periods=1).mean()
    )

# Construction de la liste finale des features
features_B = FEAT_B_BASE.copy()
for col in FEAT_B_OPT_V1 + FEAT_B_OPT_V2:
    if col in df_B_ml.columns:
        features_B.append(col)
    else:
        print(f"  [INFO] Feature '{col}' absente dans le dataset — ignorée")

lag_and_roll_B = [
    c for c in df_B_ml.columns
    if c.startswith('delta_lag_') or c.startswith('delta_roll_')
    or c.startswith('temp_c_roll_') or c.startswith('usure_roll_')
    or c in ('delta_deriv', 'delta_deriv2', 'temp_c_deriv')
]
features_B += lag_and_roll_B

df_B_ml = df_B_ml.dropna(subset=features_B + ['risque_label'])
print(f"  Features utilisées ({len(features_B)}) : {features_B}")
print(f"  Sessions après nettoyage NaN : {len(df_B_ml):,}")

# ── Split temporel Usine B ────────────────────────────────────────────────────
print("\n── Split temporel Usine B (70 / 15 / 15) ───────────────────")

train_B, val_B, test_B = temporal_split(df_B_ml)
print(f"  Train : {len(train_B):,} sessions")
print(f"  Val   : {len(val_B):,} sessions")
print(f"  Test  : {len(test_B):,} sessions")

X_train_B = train_B[features_B]
y_train_B = train_B['risque_label']
X_val_B   = val_B[features_B]
y_val_B   = val_B['risque_label']
X_test_B  = test_B[features_B]
y_test_B  = test_B['risque_label']

# Distribution dans le train avant SMOTE
print(f"\n  Distribution train avant SMOTE :")
for k, v in y_train_B.value_counts().sort_index().items():
    print(f"    {k} ({label_names[k]}) : {v:,}")

# ── SMOTE sur le jeu d'entraînement ──────────────────────────────────────────
# On applique SMOTE uniquement sur le train pour éviter le data leakage.
# k_neighbors réduit si une classe a très peu d'exemples.
print("\n── SMOTE (rééquilibrage entraînement) ───────────────────────")

min_class_count = y_train_B.value_counts().min()
k_neighbors     = min(5, min_class_count - 1)
print(f"  k_neighbors SMOTE : {k_neighbors}")

smote = SMOTE(random_state=42, k_neighbors=k_neighbors)
X_train_B_res, y_train_B_res = smote.fit_resample(X_train_B, y_train_B)

print(f"  Distribution train après SMOTE :")
for k, v in pd.Series(y_train_B_res).value_counts().sort_index().items():
    print(f"    {k} ({label_names[k]}) : {v:,}")

# ── Modèle XGBoost (Usine B v2) ───────────────────────────────────────────────
# XGBoost est plus robuste aux classes déséquilibrées que Random Forest.
# use_label_encoder=False requis depuis XGBoost 1.6.
# eval_metric='mlogloss' pour classification multiclasse.
print("\n── Entraînement XGBoost Classifier (Usine B v2) ─────────────")

xgb_B = XGBClassifier(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    use_label_encoder=False,
    eval_metric='mlogloss',
    random_state=42,
    n_jobs=-1,
)
xgb_B.fit(X_train_B_res, y_train_B_res)
print("  Modèle entraîné.")

y_pred_B       = xgb_B.predict(X_test_B)
bal_acc_B      = balanced_accuracy_score(y_test_B, y_pred_B)
report_B       = classification_report(
    y_test_B, y_pred_B,
    target_names=['Normal (0)', 'Risque (1)', 'Critique (2)'],
    digits=3,
)
cm_B = confusion_matrix(y_test_B, y_pred_B)

y_pred_val_B  = xgb_B.predict(X_val_B)
bal_acc_val_B = balanced_accuracy_score(y_val_B, y_pred_val_B)

print(f"\n  ── Métriques Usine B (XGBoost + SMOTE) ───────────")
print(f"  Validation  → Balanced Accuracy : {bal_acc_val_B:.3f}")
print(f"  Test        → Balanced Accuracy : {bal_acc_B:.3f}")
print(f"\n  Rapport de classification (jeu de test) :")
print(report_B)

# ── Graphique 1 Usine B — Matrice de confusion ────────────────────────────────
print("\n── Graphiques Usine B ───────────────────────────────────────")

class_labels = ['Normal\n(0)', 'Risque\n(1)', 'Critique\n(2)']
n_classes    = 3

cm_norm = cm_B.astype(float) / cm_B.sum(axis=1, keepdims=True)

fig, ax = plt.subplots(figsize=(7, 6))

cmap = LinearSegmentedColormap.from_list(
    'mecha_cm', ['white', COLOR_PRIMARY], N=256
)
im = ax.imshow(cm_norm, interpolation='nearest', cmap=cmap, vmin=0, vmax=1)
plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04,
             label='Proportion (recall par classe)')

ax.set_xticks(range(n_classes))
ax.set_yticks(range(n_classes))
ax.set_xticklabels(class_labels, fontsize=10)
ax.set_yticklabels(class_labels, fontsize=10)
ax.set_xlabel('Classe prédite')
ax.set_ylabel('Classe réelle')
ax.set_title(
    f'Usine B — Matrice de confusion (normalisée) · XGBoost + SMOTE\n'
    f'Balanced Accuracy = {bal_acc_B:.3f}',
    pad=12
)

for i in range(n_classes):
    for j in range(n_classes):
        text_color = 'white' if cm_norm[i, j] > 0.55 else '#222222'
        ax.text(j, i,
                f'{cm_norm[i, j]:.2f}\n({cm_B[i, j]})',
                ha='center', va='center',
                fontsize=10, color=text_color, fontweight='bold')

fig.tight_layout()
generated_files.append(save_figure(fig, 'ml_usine_B_confusion_matrix.png'))

# ── Graphique 2 Usine B — Importance des features ─────────────────────────────
importances_B = pd.Series(
    xgb_B.feature_importances_, index=features_B
).sort_values(ascending=True).tail(15)

fig, ax = plt.subplots(figsize=(9, 5))

bars = ax.barh(importances_B.index, importances_B.values,
               color=COLOR_PRIMARY, alpha=0.80, edgecolor='white', height=0.65)
ax.set_title(
    'Usine B — Importance des features (XGBoost Classifier)', pad=12
)
ax.set_xlabel('Importance relative')
ax.set_xlim(right=importances_B.values.max() * 1.15)

for bar, val in zip(bars, importances_B.values):
    ax.text(val + importances_B.values.max() * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f'{val:.3f}', va='center', ha='left', fontsize=9, color='#333333')

fig.tight_layout()
generated_files.append(save_figure(fig, 'ml_usine_B_importances.png'))

# ── Graphique 3 Usine B — Distribution des classes (réelles vs prédites) ──────
counts_real = pd.Series(y_test_B).value_counts().sort_index()
counts_pred = pd.Series(y_pred_B).value_counts().sort_index()
all_classes  = sorted(set(counts_real.index) | set(counts_pred.index))
counts_real  = counts_real.reindex(all_classes, fill_value=0)
counts_pred  = counts_pred.reindex(all_classes, fill_value=0)
labels_dist  = [label_names[c] for c in all_classes]

x     = np.arange(len(all_classes))
width = 0.35

fig, ax = plt.subplots(figsize=(7, 5))
rects1 = ax.bar(x - width / 2, counts_real.values, width,
                label='Classes réelles', color=COLOR_PRIMARY, alpha=0.80)
rects2 = ax.bar(x + width / 2, counts_pred.values, width,
                label='Classes prédites', color=COLOR_WARN, alpha=0.80)

ax.set_xticks(x)
ax.set_xticklabels(labels_dist)
ax.set_title(
    'Usine B — Distribution classes réelles vs prédites (XGBoost + SMOTE)', pad=12
)
ax.set_ylabel('Nombre de sessions')
ax.legend()

for rect in list(rects1) + list(rects2):
    h = rect.get_height()
    ax.text(rect.get_x() + rect.get_width() / 2, h + 1,
            str(int(h)), ha='center', va='bottom', fontsize=9)

fig.tight_layout()
generated_files.append(save_figure(fig, 'ml_usine_B_distribution_classes.png'))

# =============================================================================
# RÉSUMÉ FINAL
# =============================================================================

print("\n" + "=" * 65)
print("  RÉSUMÉ FINAL — PoC Machine Learning MECHA")
print("=" * 65)

print("""
  USINE A — Prédiction RUL (Durée de vie résiduelle)
  ─────────────────────────────────────────────────
  Modèle       : Random Forest Regressor (200 arbres)
  Cible        : sessions restantes avant prochain remplacement outil
  Split        : temporel 70 / 15 / 15 (sans mélange)""")
print(f"  MAE (test)   : {mae_A:.2f} sessions")
print(f"  RMSE (test)  : {rmse_A:.2f} sessions")
print(f"  R² (test)    : {r2_A:.3f}")

print("""
  USINE B — Classification risque thermique
  ─────────────────────────────────────────────────
  Modèle       : XGBoost Classifier (300 arbres) + SMOTE
  Cible        : Normal (0) / Risque (1) / Critique (2)
  Horizon      : Critique ≤ 3 sessions · Risque ≤ 48 sessions
  Split        : temporel 70 / 15 / 15 (sans mélange)
  Priorité     : minimiser les faux négatifs CRITIQUE""")
print(f"  Balanced Acc : {bal_acc_B:.3f}")

print("\n  Fichiers PNG générés :")
for f in generated_files:
    print(f"    {f.name}")

print("\n  Ce PoC illustre la faisabilité d'une couche IA prédictive")
print("  intégrée dans l'architecture Medallion de MECHA.")
print("  Les modèles sont entraînés sur données simulées (AI4I 2020)")
print("  et devront être recalibrés sur données terrain avant déploiement.")
print("=" * 65)