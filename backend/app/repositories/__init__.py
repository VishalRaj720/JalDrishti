"""Repositories package."""
from app.repositories.base import BaseRepository  # noqa: F401
from app.repositories.user import UserRepository  # noqa: F401
from app.repositories.district import DistrictRepository, BlockRepository  # noqa: F401
from app.repositories.aquifer import AquiferRepository  # noqa: F401
from app.repositories.isr_point import IsrPointRepository  # noqa: F401
from app.repositories.simulation import SimulationRepository  # noqa: F401
