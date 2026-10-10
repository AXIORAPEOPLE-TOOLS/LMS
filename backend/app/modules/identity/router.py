from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import AdminUser, CurrentUser, SessionDep
from app.core.errors import ValidationFailedError
from app.modules.identity.schemas import (
    DepartmentIn,
    DepartmentOut,
    LoginRequest,
    MeOut,
    PersonOut,
    PreferencesUpdate,
    SignupIn,
    SignupOptionsOut,
    TokenResponse,
    UploadCommitIn,
    UploadCommitOut,
    UploadPreviewOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.modules.identity.service import AuthService, UserService, people_template_csv

router = APIRouter(tags=["identity"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: LoginRequest, session: SessionDep) -> TokenResponse:
    return TokenResponse(access_token=await AuthService(session).login(data.email, data.password))


@router.get("/auth/signup-options", response_model=SignupOptionsOut)
async def signup_options(session: SessionDep) -> SignupOptionsOut:
    """Public: whether sign-up is on, and the job roles / departments to pick from."""
    return await AuthService(session).signup_options()


@router.post("/auth/signup", response_model=TokenResponse, status_code=201)
async def signup(data: SignupIn, session: SessionDep) -> TokenResponse:
    return TokenResponse(access_token=await AuthService(session).signup(data))


@router.post("/auth/token", response_model=TokenResponse, include_in_schema=False)
async def token_for_docs(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep) -> TokenResponse:
    """OAuth2 form login so the Swagger 'Authorize' button works."""
    return TokenResponse(access_token=await AuthService(session).login(form.username, form.password))


@router.get("/me", response_model=MeOut)
async def me(session: SessionDep, user: CurrentUser) -> MeOut:
    return await UserService(session).me(user)


@router.patch("/me/preferences", response_model=MeOut)
async def update_preferences(data: PreferencesUpdate, session: SessionDep, user: CurrentUser) -> MeOut:
    service = UserService(session)
    await service.update_preferences(user, data)
    return await service.me(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(session: SessionDep, _: AdminUser, q: str | None = None, department_id: UUID | None = None) -> object:
    return await UserService(session).list_users(q, department_id)


@router.get("/people", response_model=list[PersonOut])
async def people_directory(session: SessionDep, _: CurrentUser, q: str | None = None) -> object:
    """Minimal directory (name + department) for pickers such as 'hand over to'."""
    users = await UserService(session).list_users(q)
    return [user for user in users if user.is_active]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(data: UserCreate, session: SessionDep, admin: AdminUser) -> object:
    return await UserService(session).create_user(data, admin)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: UUID, data: UserUpdate, session: SessionDep, admin: AdminUser) -> object:
    return await UserService(session).update_user(user_id, data, admin)


@router.get("/users/upload/template", response_class=PlainTextResponse)
async def upload_template(_: AdminUser) -> PlainTextResponse:
    return PlainTextResponse(
        people_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="employees-template.csv"'},
    )


@router.post("/users/upload/preview", response_model=UploadPreviewOut)
async def upload_preview(file: UploadFile, session: SessionDep, _: AdminUser) -> UploadPreviewOut:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValidationFailedError("The file is larger than 5 MB.")
    return await UserService(session).preview_upload(file.filename or "upload.csv", content)


@router.post("/users/upload/commit", response_model=UploadCommitOut)
async def upload_commit(data: UploadCommitIn, session: SessionDep, admin: AdminUser) -> UploadCommitOut:
    return await UserService(session).commit_upload(data, admin)


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(session: SessionDep, _: CurrentUser) -> object:
    return await UserService(session).list_departments()


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(data: DepartmentIn, session: SessionDep, admin: AdminUser) -> object:
    return await UserService(session).create_department(data, admin)
