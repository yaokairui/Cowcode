"""Team 对外导出。"""

from __future__ import annotations

from cowcode.team.manager import LeadMessage, Manager
from cowcode.team.persistence import sanitize
from cowcode.team.types import (
    BackendType,
    InProcessTeammateNoSpawnError,
    MemberExistsError,
    MemberNotFoundError,
    Team,
    TeamError,
    TeamHasActiveMembersError,
    TeamNotFoundError,
    TeammateInfo,
)

__all__ = [
    "BackendType",
    "InProcessTeammateNoSpawnError",
    "LeadMessage",
    "Manager",
    "MemberExistsError",
    "MemberNotFoundError",
    "Team",
    "TeamError",
    "TeamHasActiveMembersError",
    "TeamNotFoundError",
    "TeammateInfo",
    "sanitize",
]
