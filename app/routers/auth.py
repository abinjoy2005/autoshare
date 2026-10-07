import os

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
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


def _set_session_cookie(response: Response, token: str) -> None:
    max_age = token_lifetime_minutes() * 60
    response.set_cookie(
        "autoshare_session",
        token,
        max_age=max_age,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    payload: RegisterInput,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
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
        raise HTTPException(status_code=409, detail="An account with this email exists") from exc
    db.refresh(user)
    _set_session_cookie(response, token)
    return AuthResponse(user=UserPublic.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginInput,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _set_session_cookie(response, create_access_token(user))
    return AuthResponse(user=UserPublic.model_validate(user))


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie("autoshare_session", path="/", httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> User:
    return user
