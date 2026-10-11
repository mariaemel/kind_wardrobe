from fastapi import APIRouter, status

from app.modules.accounts import service
from app.modules.accounts.dependencies import CurrentUser, SessionDep
from app.modules.accounts.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    OrganizationAuthResponse,
    OrganizationBriefResponse,
    OrganizationRegisterRequest,
    RefreshRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(access_token: str, refresh_token: str) -> TokenResponse:
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserRegisterRequest, session: SessionDep) -> AuthResponse:
    user, access_token, refresh_token = await service.register_user(
        session, name=payload.name, email=payload.email, password=payload.password
    )
    return AuthResponse(user=UserResponse.model_validate(user), tokens=_tokens(access_token, refresh_token))


@router.post("/register/organization", response_model=OrganizationAuthResponse, status_code=status.HTTP_201_CREATED)
async def register_organization(payload: OrganizationRegisterRequest, session: SessionDep) -> OrganizationAuthResponse:
    user, organization, access_token, refresh_token = await service.register_organization(
        session, name=payload.name, email=payload.email, password=payload.password
    )
    return OrganizationAuthResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationBriefResponse.model_validate(organization),
        tokens=_tokens(access_token, refresh_token),
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, session: SessionDep) -> AuthResponse:
    user, access_token, refresh_token = await service.login(
        session, email=payload.email, password=payload.password
    )
    return AuthResponse(user=UserResponse.model_validate(user), tokens=_tokens(access_token, refresh_token))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(payload: RefreshRequest, session: SessionDep) -> AuthResponse:
    user, access_token, refresh_token = await service.refresh_tokens(session, payload.refresh_token)
    return AuthResponse(user=UserResponse.model_validate(user), tokens=_tokens(access_token, refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, session: SessionDep) -> None:
    await service.logout(session, payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
