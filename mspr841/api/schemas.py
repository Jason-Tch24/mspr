"""
schemas.py — Modèles Pydantic pour l'API MECHA IA
Définit les structures d'entrée et de sortie des deux endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─────────────────────────────────────────────────────────────
# USINE A — Prédiction RUL (Remaining Useful Life)
# ─────────────────────────────────────────────────────────────

class RULInput(BaseModel):
    """Capteurs et KPIs courants de l'Usine A pour prédire la RUL."""

    usure_cumulee_pct: float = Field(..., ge=0, le=100,
        description="Usure cumulée de l'outil en % (0=neuf, 90=limite)")
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
    rul_heures: float   = Field(..., description="Heures restantes avant remplacement (1 session = 30 min)")
    usure_cumulee_pct: float
    niveau_alerte: str  = Field(..., description="OK | WARNING | CRITICAL")
    interpretation: str
    modele: str


# ─────────────────────────────────────────────────────────────
# USINE B — Classification du risque thermique
# ─────────────────────────────────────────────────────────────

class RisqueThermInput(BaseModel):
    """Capteurs et KPIs courants de l'Usine B pour classifier le risque thermique."""

    temp_process_delta: float = Field(...,
        description="Delta thermique process / air ambiant (K)")
    TRS: float = Field(..., ge=0, le=1,
        description="Taux de Rendement Synthétique (0–1)")
    taux_rebut: Optional[float] = Field(None, ge=0, le=1)
    disponibilite: Optional[float] = Field(None, ge=0, le=1)
    performance: Optional[float] = Field(None, ge=0, le=1)
    consommation_kwh: Optional[float] = Field(None, ge=0)
    temps_cycle_min: Optional[float] = Field(None, ge=0)
    derive_cycle_pct: Optional[float] = Field(None)
    nb_pannes_7j: Optional[int] = Field(None, ge=0,
        description="Nombre de pannes sur les 7 derniers jours")
    temp_process_c: Optional[float] = Field(None,
        description="Température absolue process (°C)")
    usure_cumulee_pct: Optional[float] = Field(None, ge=0, le=100)
    couple_nm: Optional[float] = Field(None, ge=0)
    vitesse_rotation_rpm: Optional[float] = Field(None, ge=0)
    indice_stabilite_process: Optional[float] = Field(None, ge=0, le=1,
        description="Indice de stabilité process (0=instable, 1=stable)")
    panne_usure_outil: Optional[int] = Field(None, ge=0, le=1,
        description="Panne par usure outil en cours (0/1)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "temp_process_delta": 9.5,
                "TRS": 0.93,
                "taux_rebut": 0.03,
                "disponibilite": 0.97,
                "performance": 0.98,
                "consommation_kwh": 3.5,
                "temps_cycle_min": 40.0,
                "derive_cycle_pct": 5.0,
                "nb_pannes_7j": 8,
                "temp_process_c": 34.0,
                "usure_cumulee_pct": 42.0,
                "couple_nm": 45.0,
                "vitesse_rotation_rpm": 1530,
                "indice_stabilite_process": 0.89,
                "panne_usure_outil": 0,
            }
        }
    }


class RisqueThermOutput(BaseModel):
    """Résultat de la classification risque thermique pour l'Usine B."""

    usine: str
    risque_label: int   = Field(..., description="0=Normal · 1=Risque · 2=Critique")
    risque_nom: str     = Field(..., description="Normal | Risque | Critique")
    probabilites: dict  = Field(..., description="Probabilité par classe (0, 1, 2)")
    niveau_alerte: str  = Field(..., description="OK | WARNING | CRITICAL")
    interpretation: str
    modele: str
