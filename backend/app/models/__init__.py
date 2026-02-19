"""Models package – imports all ORM classes so SQLAlchemy metadata is populated."""
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.district import District  # noqa: F401
from app.models.block import Block  # noqa: F401
from app.models.aquifer import Aquifer, AquiferType  # noqa: F401
from app.models.isr_point import IsrPoint  # noqa: F401
from app.models.simulation import Simulation, SimulationAquifer, PlumeParameter  # noqa: F401
from app.models.monitoring_data import MonitoringData  # noqa: F401
from app.models.hydraulic_head import HydraulicHead  # noqa: F401
from app.models.ml_model import MLModel, MLModelType  # noqa: F401

__all__ = [
    "User", "UserRole",
    "District",
    "Block",
    "Aquifer", "AquiferType",
    "IsrPoint",
    "Simulation", "SimulationAquifer", "PlumeParameter",
    "MonitoringData",
    "HydraulicHead",
    "MLModel", "MLModelType",
]
