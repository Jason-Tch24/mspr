"""
schemas.py — Contrat d'entrée / sortie de l'API MECHA IA (modèles Pydantic).
"""

from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# USINE A — Prédiction RUL (Remaining Useful Life)
# ─────────────────────────────────────────────────────────────

class RULInput(BaseModel):
    """Capteurs et KPIs courants de l'Usine A. Seuls l'usure et le TRS sont obligatoires ;
    les champs absents sont remplacés par la médiane observée à l'entraînement."""

    usure_cumulee_pct: float = Field(..., ge=0, le=100,
        description="Usure cumulée de l'outil en % (0 = neuf, 90 = limite de remplacement)")
    TRS: float = Field(..., ge=0, le=1,
        description="Taux de Rendement Synthétique (0–1)")
    temps_cycle_min: Optional[float] = Field(None, ge=0,
        description="Temps de cycle mesuré (minutes)")
    derive_cycle_pct: Optional[float] = Field(None,
        description="Dérive du temps de cycle par rapport au nominal (%)")
    disponibilite: Optional[float] = Field(None, ge=0, le=1,
        description="Taux de disponibilité machine (0–1)")
    performance: Optional[float] = Field(None, ge=0, le=1,
        description="Taux de performance (0–1)")
    qualite: Optional[float] = Field(None, ge=0, le=1,
        description="Taux de qualité (0–1)")
    consommation_kwh: Optional[float] = Field(None, ge=0,
        description="Consommation énergétique par session (kWh)")
    vitesse_rotation_rpm: Optional[float] = Field(None, ge=0,
        description="Vitesse de rotation outil (tr/min)")
    couple_nm: Optional[float] = Field(None, ge=0,
        description="Couple de coupe (N·m)")
    taux_rebut: Optional[float] = Field(None, ge=0, le=1,
        description="Taux de rebut instantané (0–1)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "usure_cumulee_pct": 45.2,
                "TRS": 0.92,
                "temps_cycle_min": 44.5,
                "derive_cycle_pct": 12.3,
                "disponibilite": 0.97,
                "performance": 0.98,
                "qualite": 0.95,
                "consommation_kwh": 3.1,
                "vitesse_rotation_rpm": 1500,
                "couple_nm": 40.0,
                "taux_rebut": 0.04,
            }
        }
    }


class RULOutput(BaseModel):
    """Résultat de la prédiction RUL pour l'Usine A."""

    usine: str
    rul_sessions: float = Field(..., description="Sessions restantes avant remplacement outil")
    rul_heures: float = Field(..., description="Heures restantes (1 session = 30 min)")
    usure_cumulee_pct: float
    niveau_alerte: str = Field(..., description="OK | WARNING | CRITICAL")
    interpretation: str
    modele: str


# ─────────────────────────────────────────────────────────────
# USINE B — Risque de panne thermique à 24 h
# ─────────────────────────────────────────────────────────────

class RisqueThermInput(BaseModel):
    """Mesures thermiques de l'Usine B.

    Le modèle évalue le régime thermique : il a besoin du delta courant et,
    idéalement, des deltas des sessions précédentes (`historique_delta`).
    Les autres champs sont acceptés pour compatibilité avec les dashboards
    mais ne sont pas utilisés par le modèle."""

    temp_process_delta: float = Field(..., ge=0, le=60,
        description="Delta thermique process / air ambiant de la session courante (K)")
    historique_delta: Optional[list[float]] = Field(None, max_length=500,
        description="Deltas des sessions précédentes, de la plus ancienne à la plus récente, "
                    "session courante exclue. 47 valeurs couvrent les 24 h utilisées par le modèle.")
    TRS: Optional[float] = Field(None, ge=0, le=1)
    taux_rebut: Optional[float] = Field(None, ge=0, le=1)
    disponibilite: Optional[float] = Field(None, ge=0, le=1)
    performance: Optional[float] = Field(None, ge=0, le=1)
    consommation_kwh: Optional[float] = Field(None, ge=0)
    temps_cycle_min: Optional[float] = Field(None, ge=0)
    derive_cycle_pct: Optional[float] = Field(None)
    nb_pannes_7j: Optional[int] = Field(None, ge=0)
    temp_process_c: Optional[float] = Field(None)
    usure_cumulee_pct: Optional[float] = Field(None, ge=0, le=100)
    couple_nm: Optional[float] = Field(None, ge=0)
    vitesse_rotation_rpm: Optional[float] = Field(None, ge=0)
    indice_stabilite_process: Optional[float] = Field(None, ge=0, le=1)
    panne_usure_outil: Optional[int] = Field(None, ge=0, le=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "temp_process_delta": 9.1,
                "historique_delta": [9.8, 9.6, 9.9, 9.4, 9.3, 9.5, 9.2, 9.0, 9.3, 8.9, 9.1],
            }
        }
    }


class RisqueThermOutput(BaseModel):
    """Résultat de l'évaluation du risque thermique pour l'Usine B."""

    usine: str
    probabilite_panne_24h: float = Field(...,
        description="Probabilité estimée d'au moins une panne thermique dans les 24 h (0–1)")
    risque_label: int = Field(..., description="0 = Normal · 1 = À risque · 2 = Critique")
    risque_nom: str = Field(..., description="Normal | À risque | Critique")
    probabilites: dict = Field(..., description="{'Normal': 1 − p, 'À risque': p}")
    niveau_alerte: str = Field(..., description="OK | WARNING | CRITICAL")
    interpretation: str
    mode_degrade: bool = Field(...,
        description="True si aucun historique n'a été fourni : le régime thermique est "
                    "alors estimé à partir de la seule valeur courante (moins fiable).")
    nb_sessions_historique: int = Field(..., description="Nombre de sessions d'historique utilisées")
    modele: str
