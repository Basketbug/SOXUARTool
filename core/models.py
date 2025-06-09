# =============================================================================
# core/models.py - Unified data models
# =============================================================================

from dataclasses import dataclass, field
from typing import Dict, Any
from enum import Enum


class LookupMethod(Enum):
    """Enumeration of AD lookup methods"""
    PRIMARY = "primary"
    BACKUP = "backup"
    DISPLAYNAME = "displayname"
    NAME_COMPONENTS = "name_components"
    EMAIL = "email"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class UserRecord:
    """Unified user record model"""
    username: str
    email: str = ""
    full_name: str = ""
    department: str = ""
    title: str = ""
    is_active: bool = False
    lookup_method: LookupMethod = LookupMethod.FAILED
    original_identifier: str = ""
    csv_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleRecord:
    """Role assignment record"""
    username: str
    department: str
    title: str
    assigned_roles: str


@dataclass
class ProcessingStats:
    """Statistics for processing results"""
    total_records: int = 0
    successful_lookups: int = 0
    failed_lookups: int = 0
    error_lookups: int = 0
    lookup_method_counts: Dict[LookupMethod, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_records == 0:
            return 0.0
        return (self.successful_lookups / self.total_records) * 100