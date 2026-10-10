from datetime import date
from typing import Any
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.shared.schemas import Schema


class LoginRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=1)


class SignupIn(Schema):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8)
    job_role_id: UUID
    department_id: UUID | None = None


class SignupChoice(Schema):
    id: UUID
    name: str
    group: str = ""


class SignupOptionsOut(Schema):
    allowed: bool
    email_domains: list[str]
    roles: list[SignupChoice]
    departments: list[SignupChoice]


class TokenResponse(Schema):
    access_token: str
    token_type: str = "bearer"


class DepartmentOut(Schema):
    id: UUID
    name: str
    head_id: UUID | None


class DepartmentIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    head_id: UUID | None = None


class UserOut(Schema):
    id: UUID
    email: str
    full_name: str
    employee_code: str | None
    system_roles: list[str]
    is_active: bool
    department_id: UUID | None
    job_role_id: UUID | None
    manager_id: UUID | None
    joined_on: date | None
    phone: str | None = None
    locale: str
    show_name_on_boards: bool
    reminder_window: list[str]
    reminder_channels: dict[str, Any]
    hours_per_week: int


class PersonOut(Schema):
    id: UUID
    full_name: str
    department_id: UUID | None
    job_role_id: UUID | None


class MeOut(UserOut):
    department_name: str | None = None
    job_role_name: str | None = None
    manager_name: str | None = None
    can_open_knowledge: bool = False


class UserCreate(Schema):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8)
    employee_code: str | None = None
    system_roles: list[str] = ["learner"]
    department_id: UUID | None = None
    job_role_id: UUID | None = None
    manager_id: UUID | None = None
    joined_on: date | None = None


class UserUpdate(Schema):
    full_name: str | None = None
    system_roles: list[str] | None = None
    department_id: UUID | None = None
    job_role_id: UUID | None = None
    manager_id: UUID | None = None
    is_active: bool | None = None


_TIME = r"^([01]\d|2[0-3]):[0-5]\d$"


class PreferencesUpdate(Schema):
    locale: str | None = Field(default=None, pattern="^(en|hi)$")
    show_name_on_boards: bool | None = None
    reminder_window: list[str] | None = None
    reminder_channels: dict[str, bool] | None = None
    hours_per_week: int | None = Field(default=None, ge=1, le=40)
    phone: str | None = Field(default=None, max_length=20, pattern=r"^$|^\+?[0-9 ()-]{7,20}$")

    @field_validator("reminder_window")
    @classmethod
    def _valid_window(cls, value: list[str] | None) -> list[str] | None:
        import re

        if value is None:
            return value
        if len(value) != 2 or not all(re.match(_TIME, v) for v in value) or value[0] >= value[1]:
            raise ValueError("Choose a start and end time, for example 11:00 to 13:00.")
        return value


class UploadRowOut(Schema):
    row: int
    full_name: str
    email: str
    job_title: str
    department: str | None
    status: str  # ready | needs_role | error
    job_role_id: UUID | None = None
    suggested_role_id: UUID | None = None
    suggested_role_name: str | None = None
    message: str | None = None


class UploadPreviewOut(Schema):
    rows: list[UploadRowOut]
    ready: int
    needs_role: int
    errors: int


class UploadCommitRow(Schema):
    full_name: str
    email: EmailStr
    job_role_id: UUID
    department: str | None = None
    employee_code: str | None = None


class UploadCommitIn(Schema):
    rows: list[UploadCommitRow]


class UploadCommitOut(Schema):
    created: int
    skipped: int
