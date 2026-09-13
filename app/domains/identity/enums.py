"""Identity domain enumerations.

Stored as strings in the database so SQLite and PostgreSQL stay compatible.
"""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class EnterpriseMemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class EnterpriseMemberStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
