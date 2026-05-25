# ─────────────────────────────────────────────────────────────
# Dockerfile — API FastAPI MECHA (MSPR 841)
#
# Build : docker build -t mecha-api .         (depuis mspr841/api/)
# Run   : docker run -p 8000:8000 mecha-api
# Docs  : http://localhost:8000/docs
#
# IMPORTANT : les modèles .joblib ne sont PAS inclus dans l'image
# (exclus par .gitignore). Pour les activer en production :
#   1. Exécuter python notebooks/ml_poc_mecha_rul_thermique.py
#   2. Copier rf_usine_A_rul.joblib et xgb_usine_B_risque.joblib
#      dans mspr841/api/models/ avant de rebuilder l'image.
# Sans modèles l'API démarre en mode dégradé (_models_ok = False).
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances en premier pour profiter du cache layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source et les métadonnées de modèles
COPY main.py schemas.py ./
COPY models/ models/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
