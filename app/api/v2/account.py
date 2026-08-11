from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.schemas.auth import (
    AccountExportResponse,
    AuthenticatedUserResponse,
    DeleteAccountRequest,
)
from app.services.account_service import delete_account_data, export_account_data


router = APIRouter(tags=["account-v2"])


@router.get("/me", response_model=AuthenticatedUserResponse)
def get_me(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
) -> AuthenticatedUserResponse:
    user = authenticated.user
    return AuthenticatedUserResponse(
        public_id=user.public_id,
        name=user.name,
        email=user.email,
        timezone=user.timezone,
    )


@router.get("/account/export", response_model=AccountExportResponse)
def export_account(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> AccountExportResponse:
    return export_account_data(db, authenticated.user)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    _request: DeleteAccountRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> Response:
    delete_account_data(db, authenticated.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
