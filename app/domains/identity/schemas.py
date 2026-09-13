"""Identity HTTP and resolver schemas. CurrentIdentity is not a table."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.identity.enums import EnterpriseMemberRole, EnterpriseMemberStatus, UserStatus


class CurrentIdentity(BaseModel):
    user_id: UUID
    enterprise_id: UUID
    membership_id: UUID
    role: EnterpriseMemberRole


class MeUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    status: UserStatus


class MeEnterprise(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class MeMembership(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: EnterpriseMemberRole
    status: EnterpriseMemberStatus


class MeResponse(BaseModel):
    user: MeUser
    enterprise: MeEnterprise
    membership: MeMembership
