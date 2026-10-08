import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import AuthResponse, LoginInput, RegisterInput, UserPublic
from app.security import (
    create_access_token,
    get_current_user,
    hash_password,
    token_lifetime_minutes,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _cookie_is_secure(request: Request) -> bool:
    configured = os.getenv("COOKIE_SECURE")
    if configured is None:
        return request.url.scheme == "https"
    configured = configured.strip().lower()
    if configured not in {"true", "false"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COOKIE_SECURE must be true or false",
        )
    return configured == "true"


def _set_session_cookie(response: Response, token: str, secure: bool) -> None:
    max_age = token_lifetime_minutes() * 60
    response.set_cookie(
        "autoshare_session",
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    payload: RegisterInput,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    secure_cookie = _cookie_is_secure(request)
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email exists")

    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_verified=False,
    )
    db.add(user)
    try:
        db.flush()
        token = create_access_token(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
            raise HTTPException(
                status_code=409, detail="An account with this email exists"
            ) from exc
        raise
    db.refresh(user)
    _set_session_cookie(response, token, secure_cookie)
    return AuthResponse(user=UserPublic.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginInput,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    secure_cookie = _cookie_is_secure(request)
    email = str(payload.email).lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _set_session_cookie(response, create_access_token(user), secure_cookie)
    return AuthResponse(user=UserPublic.model_validate(user))


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie("autoshare_session", path="/", httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> User:
    return user
