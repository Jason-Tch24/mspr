# ─────────────────────────────────────────────────────────────
# Dockerfile — Dashboards Dash MECHA (MSPR 831)
#
# CONTEXTE DE BUILD : racine du dépôt (mspr_jason/)
# Le build context doit inclure dashboard/ ET data/ car config.py
# calcule ROOT = Path(__file__).parent.parent (= /app dans le conteneur).
#
# Usage via docker-compose (recommandé) :
#   docker compose up dashboard_groupe
#
# Build manuel (depuis la racine du dépôt) :
#   docker build -f dashboard/Dockerfile -t mecha-dashboard .
#
# Variable APP_MODULE : nom du script à exécuter (sans .py)
#   app_groupe    → port 8050  (vue groupe)
#   app_usine_A   → port 8051  (Usine A — Lyon)
#   app_usine_B   → port 8052  (Usine B — Bordeaux)
#   app_usine_C   → port 8053  (Usine C — Toulouse)
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances en premier (cache layer Docker)
COPY dashboard/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copier le code dashboard et les données Gold
# Les deux répertoires doivent être présents ensemble :
# config.py résout ROOT = /app (parent du dossier dashboard)
COPY dashboard/ dashboard/
COPY data/ data/

# Le script Python est lancé depuis le dossier dashboard/
# pour que les imports locaux (store, config, etc.) fonctionnent
WORKDIR /app/dashboard

ENV APP_MODULE=app_groupe

# Shell form intentionnel : permet l'expansion de $APP_MODULE
CMD python ${APP_MODULE}.py
