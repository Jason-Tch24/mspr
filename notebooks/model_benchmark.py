"""
model_benchmark.py — Benchmark multi-modèles MECHA (MSPR 841)

Évalue 5 régresseurs (Usine A — RUL) et 5 classifieurs (Usine B — risque thermique)
via une validation croisée temporelle stricte (TimeSeriesSplit, 5 folds walk-forward).

Le meilleur modèle de chaque usine est automatiquement sauvegardé dans
mspr841/api/models/ pour être exposé par l'API FastAPI.

Lancement :
    python3 notebooks/model_benchmark.py
"""

import sys
import json
import time
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import (
    RandomForestRegressor, GradientBoostingRegressor, ExtraTreesRegressor,
    RandomForestClassifier,
)
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline as SkPipeline
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    balanced_accuracy_score, recall_score, f1_score,
)
from xgboost import XGBRegressor, XGBClassifier
from imblearn.over_sampling import SMOTE
from imblearn.ensemble import BalancedRandomForestClassifier, EasyEnsembleClassifier

# ─────────────────────────────────────────────────────────────
# CHEMINS
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_GOLD   = PROJECT_DIR / 'data' / 'gold'
MODELS_DIR  = PROJECT_DIR / 'mspr841' / 'api' / 'models'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

PATH_A = DATA_GOLD / 'usine_A.parquet'
PATH_B = DATA_GOLD / 'usine_B.parquet'

N_SPLITS = 5   # folds temporels walk-forward

# ─────────────────────────────────────────────────────────────
# AFFICHAGE
# ─────────────────────────────────────────────────────────────

def header(title: str) -> None:
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)

def subheader(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 60 - len(title))}")

def table_regression(results: dict) -> None:
    print(f"\n  {'Modèle':<36} {'MAE (↓)':>12} {'RMSE (↓)':>12} {'R² (↑)':>11}")
    print("  " + "─" * 74)
    for name, m in sorted(results.items(), key=lambda x: x[1]['mae_mean']):
        marker = " ◄ MEILLEUR" if m.get('best') else ""
        print(
            f"  {name:<36}"
            f"  {m['mae_mean']:5.2f} ±{m['mae_std']:4.2f}"
            f"  {m['rmse_mean']:5.2f} ±{m['rmse_std']:4.2f}"
            f"  {m['r2_mean']:5.3f} ±{m['r2_std']:4.3f}"
            f"{marker}"
        )

def table_classification(results: dict) -> None:
    print(f"\n  {'Modèle':<38} {'BalAcc (↑)':>11} {'Rec.Crit (↑)':>13} {'F1-macro (↑)':>13}")
    print("  " + "─" * 78)
    for name, m in sorted(results.items(), key=lambda x: -x[1]['recall_critique_mean']):
        marker = " ◄ MEILLEUR" if m.get('best') else ""
        print(
            f"  {name:<38}"
            f"  {m['bal_acc_mean']:5.3f} ±{m['bal_acc_std']:4.3f}"
            f"  {m['recall_critique_mean']:6.3f} ±{m['recall_critique_std']:5.3f}"
            f"  {m['f1_macro_mean']:6.3f} ±{m['f1_macro_std']:5.3f}"
            f"{marker}"
        )

# ─────────────────────────────────────────────────────────────
# FEATURE ENGINEERING USINE A
# ─────────────────────────────────────────────────────────────

def build_features_A(df: pd.DataFrame):
    """
    Construit les features et la cible RUL pour Usine A.
    Retourne (X, y, feature_names).
    """
    df = df.reset_index(drop=True).copy()
    df['remplacement_outil'] = pd.to_numeric(
        df['remplacement_outil'], errors='coerce'
    ).fillna(0)

    # Cible RUL : backward fill depuis chaque remplacement
    rul = np.zeros(len(df), dtype=float)
    prev = None
    for i in reversed(range(len(df))):
        if df.loc[i, 'remplacement_outil'] == 1:
            rul[i] = 0
            prev = i
        elif prev is not None:
            rul[i] = prev - i
        else:
            rul[i] = 0
    df['rul_target'] = rul
    df = df[df['rul_target'] > 0].copy()

    # Lags et rolling usure
    for lag in [1, 2, 3, 5]:
        df[f'usure_lag_{lag}'] = df['usure_cumulee_pct'].shift(lag)
    for w in [5, 10, 20]:
        df[f'usure_roll_mean_{w}'] = df['usure_cumulee_pct'].rolling(w, min_periods=1).mean()
        df[f'usure_roll_std_{w}']  = df['usure_cumulee_pct'].rolling(w, min_periods=1).std().fillna(0)
    df['usure_delta'] = df['usure_cumulee_pct'].diff().fillna(0)

    base  = ['usure_cumulee_pct', 'TRS']
    opt   = ['temps_cycle_min', 'derive_cycle_pct', 'disponibilite', 'performance',
             'qualite', 'consommation_kwh', 'vitesse_rotation_rpm', 'couple_nm', 'taux_rebut']
    extra = [c for c in df.columns if c.startswith(('usure_lag_', 'usure_roll_', 'usure_delta'))]

    features = base + [c for c in opt if c in df.columns] + extra
    df = df.dropna(subset=features + ['rul_target'])

    return df[features].values, df['rul_target'].values, features

# ─────────────────────────────────────────────────────────────
# FEATURE ENGINEERING USINE B
# ─────────────────────────────────────────────────────────────

def build_features_B(df: pd.DataFrame):
    """
    Construit les features et les labels de risque thermique pour Usine B.
    Retourne (X, y, feature_names).
    """
    df = df.reset_index(drop=True).copy()

    panne_col = 'panne_thermique' if 'panne_thermique' in df.columns else 'panne_machine'
    df[panne_col] = pd.to_numeric(df[panne_col], errors='coerce').fillna(0)

    # Labels 3 classes : forward-looking
    HORIZON_CRITIQUE = 3
    HORIZON_RISQUE   = 48
    arr    = df[panne_col].values
    n      = len(df)
    labels = np.zeros(n, dtype=int)
    for i in range(n):
        fin_crit = min(i + HORIZON_CRITIQUE + 1, n)
        if arr[i + 1 : fin_crit].sum() > 0:
            labels[i] = 2
            continue
        fin_risq = min(i + HORIZON_RISQUE + 1, n)
        if arr[i + HORIZON_CRITIQUE + 1 : fin_risq].sum() > 0:
            labels[i] = 1
    df['risque_label'] = labels

    # Lags et rolling delta thermique
    for lag in [1, 2, 3, 5]:
        df[f'delta_lag_{lag}'] = df['temp_process_delta'].shift(lag)
    for w in [5, 10, 20]:
        df[f'delta_roll_mean_{w}'] = df['temp_process_delta'].rolling(w, min_periods=1).mean()
        df[f'delta_roll_std_{w}']  = df['temp_process_delta'].rolling(w, min_periods=1).std().fillna(0)
    df['delta_deriv']  = df['temp_process_delta'].diff().fillna(0)
    df['delta_deriv2'] = df['delta_deriv'].diff().fillna(0)

    if 'temp_process_c' in df.columns:
        for w in [5, 10]:
            df[f'temp_c_roll_mean_{w}'] = df['temp_process_c'].rolling(w, min_periods=1).mean()
        df['temp_c_deriv'] = df['temp_process_c'].diff().fillna(0)

    if 'usure_cumulee_pct' in df.columns:
        df['usure_roll_mean_10'] = df['usure_cumulee_pct'].rolling(10, min_periods=1).mean()

    base  = ['temp_process_delta', 'TRS']
    opt1  = ['taux_rebut', 'disponibilite', 'performance', 'consommation_kwh',
             'temps_cycle_min', 'derive_cycle_pct', 'nb_pannes_7j']
    opt2  = ['temp_process_c', 'usure_cumulee_pct', 'couple_nm', 'vitesse_rotation_rpm',
             'indice_stabilite_process', 'panne_usure_outil']
    extra = [c for c in df.columns if c.startswith(('delta_lag_', 'delta_roll_',
             'temp_c_roll_', 'usure_roll_')) or c in ('delta_deriv', 'delta_deriv2', 'temp_c_deriv')]

    features = base + [c for c in opt1 + opt2 if c in df.columns] + extra
    df = df.dropna(subset=features + ['risque_label'])

    return df[features].values, df['risque_label'].values, features

# ─────────────────────────────────────────────────────────────
# BOUCLE BENCHMARK RÉGRESSION (Usine A)
# ─────────────────────────────────────────────────────────────

def run_regression_benchmark(X, y, models: dict) -> dict:
    """
    TimeSeriesSplit walk-forward pour les régresseurs.
    Retourne un dict {nom: {mae_mean, mae_std, rmse_mean, rmse_std, r2_mean, r2_std}}.
    """
    tscv    = TimeSeriesSplit(n_splits=N_SPLITS)
    results = {}

    for name, model in models.items():
        maes, rmses, r2s = [], [], []
        t0 = time.time()

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]

            model.fit(X_tr, y_tr)
            y_pred = model.predict(X_te)

            maes.append(mean_absolute_error(y_te, y_pred))
            rmses.append(np.sqrt(mean_squared_error(y_te, y_pred)))
            r2s.append(r2_score(y_te, y_pred))

        elapsed = time.time() - t0
        results[name] = {
            'mae_mean' : np.mean(maes),
            'mae_std'  : np.std(maes),
            'rmse_mean': np.mean(rmses),
            'rmse_std' : np.std(rmses),
            'r2_mean'  : np.mean(r2s),
            'r2_std'   : np.std(r2s),
            'elapsed_s': round(elapsed, 1),
        }
        print(f"    {name:<36} MAE={np.mean(maes):.2f} ±{np.std(maes):.2f}  "
              f"R²={np.mean(r2s):.3f}  [{elapsed:.1f}s]")

    return results

# ─────────────────────────────────────────────────────────────
# BOUCLE BENCHMARK CLASSIFICATION (Usine B)
# ─────────────────────────────────────────────────────────────

def _smote_resample(X_tr, y_tr):
    """SMOTE avec k_neighbors adaptatif selon la classe minoritaire."""
    min_count   = pd.Series(y_tr).value_counts().min()
    k_neighbors = min(5, max(1, min_count - 1))
    smote       = SMOTE(random_state=42, k_neighbors=k_neighbors)
    return smote.fit_resample(X_tr, y_tr)


def run_classification_benchmark(X, y, models: dict) -> dict:
    """
    TimeSeriesSplit walk-forward pour les classifieurs.
    SMOTE appliqué uniquement sur le fold d'entraînement (pas de leakage).
    Retourne un dict avec balanced accuracy, recall Critique, F1-macro.
    """
    tscv    = TimeSeriesSplit(n_splits=N_SPLITS)
    results = {}

    for name, spec in models.items():
        model      = spec['model']
        use_smote  = spec.get('smote', False)
        use_scaler = spec.get('scaler', False)

        bal_accs, rec_crits, f1s = [], [], []
        t0 = time.time()

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]

            # Scaler optionnel (pour modèles linéaires)
            if use_scaler:
                scaler = StandardScaler()
                X_tr   = scaler.fit_transform(X_tr)
                X_te   = scaler.transform(X_te)

            # SMOTE sur le fold train uniquement
            if use_smote:
                try:
                    X_tr, y_tr = _smote_resample(X_tr, y_tr)
                except Exception:
                    pass  # si fold trop petit, entraîner sans SMOTE

            model.fit(X_tr, y_tr)
            y_pred = model.predict(X_te)

            bal_accs.append(balanced_accuracy_score(y_te, y_pred))
            # Recall classe 2 (Critique) — zero_division=0 si classe absente du fold
            rec_crits.append(
                recall_score(y_te, y_pred, labels=[2], average=None, zero_division=0)[0]
            )
            f1s.append(f1_score(y_te, y_pred, average='macro', zero_division=0))

        elapsed = time.time() - t0
        results[name] = {
            'bal_acc_mean'          : np.mean(bal_accs),
            'bal_acc_std'           : np.std(bal_accs),
            'recall_critique_mean'  : np.mean(rec_crits),
            'recall_critique_std'   : np.std(rec_crits),
            'f1_macro_mean'         : np.mean(f1s),
            'f1_macro_std'          : np.std(f1s),
            'elapsed_s'             : round(elapsed, 1),
        }
        print(f"    {name:<38} BalAcc={np.mean(bal_accs):.3f}  "
              f"RecCrit={np.mean(rec_crits):.3f}  [{elapsed:.1f}s]")

    return results

# ─────────────────────────────────────────────────────────────
# ENTRAÎNEMENT FINAL DU MEILLEUR MODÈLE (sur toutes les données)
# ─────────────────────────────────────────────────────────────

def retrain_best_regression(name, model, X, y, features, results):
    """Ré-entraîne le meilleur régresseur sur l'intégralité du dataset."""
    model.fit(X, y)
    path_model = MODELS_DIR / 'rf_usine_A_rul.joblib'
    joblib.dump(model, path_model)

    meta = {
        'usine'          : 'Usine_A',
        'type'           : 'regression',
        'algorithme'     : name,
        'features'       : features,
        'metriques_cv'   : {
            'folds'    : N_SPLITS,
            'MAE_mean' : round(results['mae_mean'], 3),
            'MAE_std'  : round(results['mae_std'], 3),
            'RMSE_mean': round(results['rmse_mean'], 3),
            'R2_mean'  : round(results['r2_mean'], 4),
        },
        'horizon_critique_sessions': 10,
        'horizon_warning_sessions' : 20,
        'session_duree_min'        : 30,
        'benchmark_date'           : datetime.now().isoformat(timespec='seconds'),
    }
    path_meta = MODELS_DIR / 'rf_usine_A_rul_meta.json'
    with open(path_meta, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n  Modèle sauvegardé → {path_model.name}")
    print(f"  Méta sauvegardée  → {path_meta.name}")


def retrain_best_classification(name, spec, X, y, features, results):
    """Ré-entraîne le meilleur classifieur sur l'intégralité du dataset."""
    model      = spec['model']
    use_smote  = spec.get('smote', False)
    use_scaler = spec.get('scaler', False)

    X_fit, y_fit = X.copy(), y.copy()

    scaler = None
    if use_scaler:
        scaler = StandardScaler()
        X_fit  = scaler.fit_transform(X_fit)

    if use_smote:
        try:
            X_fit, y_fit = _smote_resample(X_fit, y_fit)
        except Exception:
            pass

    model.fit(X_fit, y_fit)

    path_model = MODELS_DIR / 'xgb_usine_B_risque.joblib'
    # Sauvegarder le scaler dans le modèle si besoin (wrappé dans un dict)
    artifact = {'model': model, 'scaler': scaler, 'use_scaler': use_scaler}
    joblib.dump(artifact if use_scaler else model, path_model)

    meta = {
        'usine'        : 'Usine_B',
        'type'         : 'classification',
        'algorithme'   : name,
        'smote'        : use_smote,
        'features'     : features,
        'classes'      : {0: 'Normal', 1: 'Risque', 2: 'Critique'},
        'metriques_cv' : {
            'folds'                : N_SPLITS,
            'BalancedAccuracy_mean': round(results['bal_acc_mean'], 4),
            'RecallCritique_mean'  : round(results['recall_critique_mean'], 4),
            'F1Macro_mean'         : round(results['f1_macro_mean'], 4),
        },
        'benchmark_date': datetime.now().isoformat(timespec='seconds'),
    }
    path_meta = MODELS_DIR / 'xgb_usine_B_risque_meta.json'
    with open(path_meta, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n  Modèle sauvegardé → {path_model.name}")
    print(f"  Méta sauvegardée  → {path_meta.name}")

# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

header("MECHA — Benchmark multi-modèles · MSPR 841")
print(f"  TimeSeriesSplit : {N_SPLITS} folds walk-forward")
print(f"  Date            : {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ─────────────────────────────────────────────────────────────
# CHARGEMENT
# ─────────────────────────────────────────────────────────────
subheader("Chargement des données Gold")

for path in [PATH_A, PATH_B]:
    if not path.exists():
        print(f"[ERREUR] Fichier introuvable : {path}")
        sys.exit(1)
    print(f"  [OK] {path.name}  ({path.stat().st_size / 1024:.0f} Ko)")

df_A = pd.read_parquet(PATH_A)
df_B = pd.read_parquet(PATH_B)
print(f"  Usine A : {len(df_A):,} sessions · {len(df_A.columns)} colonnes")
print(f"  Usine B : {len(df_B):,} sessions · {len(df_B.columns)} colonnes")

# ─────────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────
subheader("Feature engineering")

X_A, y_A, features_A = build_features_A(df_A)
X_B, y_B, features_B = build_features_B(df_B)

print(f"  Usine A → {X_A.shape[0]:,} sessions · {X_A.shape[1]} features")
print(f"  Usine B → {X_B.shape[0]:,} sessions · {X_B.shape[1]} features")

unique_B, counts_B = np.unique(y_B, return_counts=True)
label_names = {0: 'Normal', 1: 'Risque', 2: 'Critique'}
print(f"  Usine B — distribution des classes :")
for k, c in zip(unique_B, counts_B):
    print(f"    {k} ({label_names[k]}) : {c:,} ({c/len(y_B)*100:.1f}%)")

# ═════════════════════════════════════════════════════════════
# BENCHMARK USINE A — RÉGRESSION
# ═════════════════════════════════════════════════════════════

header("USINE A — Benchmark régresseurs (RUL)")

MODELS_A = {
    'RandomForestRegressor': RandomForestRegressor(
        n_estimators=200, max_depth=15, min_samples_leaf=5,
        min_samples_split=10, random_state=42, n_jobs=-1,
    ),
    'XGBRegressor': XGBRegressor(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric='rmse', random_state=42, n_jobs=-1,
    ),
    'GradientBoostingRegressor': GradientBoostingRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42,
    ),
    'ExtraTreesRegressor': ExtraTreesRegressor(
        n_estimators=200, max_depth=15, min_samples_leaf=5,
        random_state=42, n_jobs=-1,
    ),
    'Ridge (baseline linéaire)': Ridge(alpha=1.0),
}

print(f"\n  Évaluation en cours ({N_SPLITS} folds × {len(MODELS_A)} modèles) ...\n")
results_A = run_regression_benchmark(X_A, y_A, MODELS_A)

# Sélection du meilleur (MAE minimale)
best_name_A  = min(results_A, key=lambda k: results_A[k]['mae_mean'])
results_A[best_name_A]['best'] = True

subheader("Résultats Usine A")
table_regression(results_A)
print(f"\n  ► Meilleur modèle : {best_name_A}")
print(f"    MAE  = {results_A[best_name_A]['mae_mean']:.2f} ±{results_A[best_name_A]['mae_std']:.2f} sessions")
print(f"    R²   = {results_A[best_name_A]['r2_mean']:.4f} ±{results_A[best_name_A]['r2_std']:.4f}")

# ─────────────────────────────────────────────────────────────
# Ré-entraînement final + sauvegarde Usine A
# ─────────────────────────────────────────────────────────────
subheader("Sauvegarde meilleur modèle Usine A")
best_model_A = MODELS_A[best_name_A]
retrain_best_regression(best_name_A, best_model_A, X_A, y_A, features_A, results_A[best_name_A])

# ═════════════════════════════════════════════════════════════
# BENCHMARK USINE B — CLASSIFICATION
# ═════════════════════════════════════════════════════════════

header("USINE B — Benchmark classifieurs (Risque thermique)")

MODELS_B = {
    'XGBClassifier + SMOTE': {
        'model': XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric='mlogloss',
            random_state=42, n_jobs=-1,
        ),
        'smote': True,
    },
    'BalancedRandomForest': {
        'model': BalancedRandomForestClassifier(
            n_estimators=200, max_depth=15,
            random_state=42, n_jobs=-1,
        ),
        'smote': False,
    },
    'EasyEnsembleClassifier': {
        'model': EasyEnsembleClassifier(
            n_estimators=10, random_state=42, n_jobs=-1,
        ),
        'smote': False,
    },
    'RandomForest + class_weight': {
        'model': RandomForestClassifier(
            n_estimators=200, max_depth=15, class_weight='balanced',
            random_state=42, n_jobs=-1,
        ),
        'smote': False,
    },
    'LogisticRegression + SMOTE': {
        'model': LogisticRegression(
            max_iter=1000, class_weight='balanced', random_state=42,
        ),
        'smote'  : True,
        'scaler' : True,
    },
}

print(f"\n  Évaluation en cours ({N_SPLITS} folds × {len(MODELS_B)} modèles) ...\n")
results_B = run_classification_benchmark(X_B, y_B, MODELS_B)

# Sélection du meilleur (Recall Critique maximal, Balanced Accuracy comme tiebreaker)
best_name_B = max(
    results_B,
    key=lambda k: (results_B[k]['recall_critique_mean'], results_B[k]['bal_acc_mean'])
)
results_B[best_name_B]['best'] = True

subheader("Résultats Usine B")
table_classification(results_B)
print(f"\n  ► Meilleur modèle : {best_name_B}")
print(f"    Balanced Accuracy = {results_B[best_name_B]['bal_acc_mean']:.3f} ±{results_B[best_name_B]['bal_acc_std']:.3f}")
print(f"    Recall Critique   = {results_B[best_name_B]['recall_critique_mean']:.3f} ±{results_B[best_name_B]['recall_critique_std']:.3f}")
print(f"    F1-macro          = {results_B[best_name_B]['f1_macro_mean']:.3f} ±{results_B[best_name_B]['f1_macro_std']:.3f}")

# ─────────────────────────────────────────────────────────────
# Ré-entraînement final + sauvegarde Usine B
# ─────────────────────────────────────────────────────────────
subheader("Sauvegarde meilleur modèle Usine B")
retrain_best_classification(best_name_B, MODELS_B[best_name_B], X_B, y_B, features_B, results_B[best_name_B])

# ═════════════════════════════════════════════════════════════
# EXPORT JSON DU BENCHMARK COMPLET
# ═════════════════════════════════════════════════════════════

benchmark_report = {
    'date'      : datetime.now().isoformat(timespec='seconds'),
    'n_splits'  : N_SPLITS,
    'usine_A'   : {
        'meilleur': best_name_A,
        'modeles' : {k: {m: round(v, 4) if isinstance(v, float) else v
                         for m, v in r.items()} for k, r in results_A.items()},
    },
    'usine_B'   : {
        'meilleur': best_name_B,
        'modeles' : {k: {m: round(v, 4) if isinstance(v, float) else v
                         for m, v in r.items()} for k, r in results_B.items()},
    },
}

report_path = SCRIPT_DIR / 'benchmark_results.json'
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(benchmark_report, f, ensure_ascii=False, indent=2)

header("BENCHMARK TERMINÉ")
print(f"  Usine A — Meilleur : {best_name_A}")
print(f"            MAE = {results_A[best_name_A]['mae_mean']:.2f} sessions · R² = {results_A[best_name_A]['r2_mean']:.4f}")
print(f"  Usine B — Meilleur : {best_name_B}")
print(f"            Rec.Crit = {results_B[best_name_B]['recall_critique_mean']:.3f} · BalAcc = {results_B[best_name_B]['bal_acc_mean']:.3f}")
print(f"\n  Rapport JSON → {report_path}")
print(f"  Modèles      → {MODELS_DIR}")
print()
