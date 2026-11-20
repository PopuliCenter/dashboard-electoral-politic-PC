"""Model tabel inti (T2.1).

Semua model diimpor di sini supaya Alembic autogenerate melihat seluruh metadata.
"""

from app.models.auth import Role, User
from app.models.base import Base
from app.models.election import CandidatePair, Election, Party
from app.models.enums import (
    CrosswalkRelation,
    DataStatus,
    ElectionType,
    JobStatus,
    RegionLevel,
    RoleCode,
    ValidationStatus,
)
from app.models.provenance import AuditLog, DatasetVersion, DataSource, IngestionJob
from app.models.region import Region, RegionCrosswalk
from app.models.result import CandidateResult, ElectionResult, RegionTurnout

__all__ = [
    "AuditLog",
    "Base",
    "CandidatePair",
    "CandidateResult",
    "CrosswalkRelation",
    "DataSource",
    "DataStatus",
    "DatasetVersion",
    "Election",
    "ElectionResult",
    "ElectionType",
    "IngestionJob",
    "JobStatus",
    "Party",
    "Region",
    "RegionCrosswalk",
    "RegionLevel",
    "RegionTurnout",
    "Role",
    "RoleCode",
    "User",
    "ValidationStatus",
]
