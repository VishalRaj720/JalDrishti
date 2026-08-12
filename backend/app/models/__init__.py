"""Models package – imports all ORM classes so SQLAlchemy metadata is populated.

Every table in the database must be represented here. Five tables
(`contamination_events`, `hydraulic_heads`, `ml_models`, `piezometric_heads`,
`spatial_analysis_results`) were orphaned when their models were deleted without
a matching migration; `0006_drop_orphan_tables` removed them, and
`tests/test_schema_integrity.py` now fails if the two ever diverge again.
"""
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin  # noqa: F401
from app.models.org import Org  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.district import District  # noqa: F401
from app.models.block import Block  # noqa: F401
from app.models.aquifer import Aquifer, AquiferType  # noqa: F401
from app.models.isr_point import IsrPoint  # noqa: F401
from app.models.simulation import Simulation, SimulationAquifer, PlumeParameter  # noqa: F401
from app.models.monitoring_station import MonitoringStation, GroundwaterLevelReading  # noqa: F401

# Data ingestion + Month 3 monitoring
from app.models.data_source import DataSource  # noqa: F401
from app.models.monitoring_well import MonitoringWell  # noqa: F401
from app.models.water_sample import WaterSample  # noqa: F401

# P1: provenance spine + audit trail
from app.models.dataset_version import DatasetVersion  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.simulation_run import SimulationRun  # noqa: F401
from app.models.scenario import Scenario  # noqa: F401
from app.models.field_observation import (  # noqa: F401
    FieldObservation, OreObservation, ObservationType,
    ObservationOperation, ObservationStatus,
)

__all__ = [
    "Org",
    "User", "UserRole",
    "District",
    "Block",
    "Aquifer", "AquiferType",
    "IsrPoint",
    "Simulation", "SimulationAquifer", "PlumeParameter",
    "MonitoringStation", "GroundwaterLevelReading",
    "DataSource",
    "MonitoringWell",
    "WaterSample",
    "DatasetVersion",
    "AuditLog",
    "SimulationRun",
    "Scenario",
    "FieldObservation", "OreObservation",
    "ObservationType", "ObservationOperation", "ObservationStatus",
]
