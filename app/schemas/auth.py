from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str | None = Field(default=None, min_length=1, max_length=128)


class AuthChallengeResponse(BaseModel):
    state: str
    nonce: str
    expires_at: datetime


class DeviceMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str | None = Field(default=None, min_length=1, max_length=128)
    device_name: str | None = Field(default=None, min_length=1, max_length=128)
    platform: str | None = Field(default=None, min_length=1, max_length=32)
    os_version: str | None = Field(default=None, min_length=1, max_length=64)


class AppleSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_token: str = Field(min_length=1, max_length=16_000)
    state: str = Field(min_length=1, max_length=256)
    nonce: str = Field(min_length=1, max_length=256)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    device: DeviceMetadataRequest


class RefreshSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=32, max_length=256)


class AuthenticatedUserResponse(BaseModel):
    public_id: UUID
    name: str | None
    email: str | None
    timezone: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class SignInResponse(TokenPairResponse):
    user: AuthenticatedUserResponse


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE"]


class AccountExportProfile(BaseModel):
    public_id: UUID
    name: str | None
    email: str | None
    timezone: str
    work_start_time: str | None
    work_end_time: str | None
    sleep_time: str | None
    created_at: datetime


class AccountExportResponse(BaseModel):
    exported_at: datetime
    profile: AccountExportProfile
    goals: list[dict]
    tasks: list[dict]
    routines: list[dict]
    resource_budget: dict | None
    onboarding_previews: list[dict]
