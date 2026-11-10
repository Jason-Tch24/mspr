# ─────────────────────────────────────────────────────────────
# Dockerfile — API FastAPI MECHA (MSPR TPRE841)
#
# Build : docker build -t mecha-api ./mspr841/api
# Run   : docker run -p 8000:8000 mecha-api
# Docs  : http://localhost:8000/docs
#
# Les modèles (models/*.joblib + *_meta.json) sont versionnés dans le dépôt
# et embarqués dans l'image : l'image est autonome et reproductible.
# Pour les régénérer : python mspr841/ml/train_models.py
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# Dépendances d'abord, pour profiter du cache de couches Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Exécution sans privilèges : les fichiers appartiennent à l'utilisateur applicatif
RUN useradd --create-home mecha
COPY --chown=mecha:mecha main.py schemas.py features.py regles_metier.json ./
COPY --chown=mecha:mecha models/ models/
USER mecha

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,json,sys; sys.exit(0 if json.load(urllib.request.urlopen('http://localhost:8000/'))['modeles_ok'] else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
