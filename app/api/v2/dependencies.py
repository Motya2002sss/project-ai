from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import AppSession
from app.models.user import User
from app.services.auth_service import AuthError, authenticate_session


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedRequest:
    user: User
    session: AppSession
    access_token: str


def invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_authenticated_request(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthenticatedRequest:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise invalid_credentials()
    try:
        authenticated = authenticate_session(db, credentials.credentials)
    except AuthError as error:
        raise invalid_credentials() from error
    return AuthenticatedRequest(
        user=authenticated.user,
        session=authenticated.session,
        access_token=credentials.credentials,
    )
