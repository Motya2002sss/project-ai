from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.v2.dependencies import (
    AuthenticatedRequest,
    get_authenticated_request,
    invalid_credentials,
)
from app.auth.apple import AppleTokenVerifier, AppleVerificationError
from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import (
    AppleSignInRequest,
    AuthChallengeRequest,
    AuthChallengeResponse,
    AuthenticatedUserResponse,
    DogfoodSignInRequest,
    RefreshSessionRequest,
    SignInResponse,
    TokenPairResponse,
)
from app.services.auth_service import (
    AuthError,
    DeviceMetadata,
    SessionPair,
    consume_auth_challenge,
    create_auth_challenge,
    revoke_all_sessions,
    revoke_session,
    rotate_session,
    sign_in_with_apple,
    sign_in_for_local_dogfood,
)
from app.services.user_service import get_or_create_user_by_external_id


router = APIRouter(prefix="/auth", tags=["auth-v2"])
dogfood_bearer = HTTPBearer(auto_error=False)


def get_apple_verifier() -> AppleTokenVerifier:
    if not settings.apple_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Apple authentication is not configured",
        )
    return AppleTokenVerifier(
        client_id=settings.apple_client_id,
        jwks_url=settings.apple_jwks_url,
    )


@router.post("/challenge", response_model=AuthChallengeResponse)
def begin_authentication(
    request: AuthChallengeRequest,
    db: Session = Depends(get_db),
) -> AuthChallengeResponse:
    challenge = create_auth_challenge(db, device_id=request.device_id)
    return AuthChallengeResponse(
        state=challenge.state,
        nonce=challenge.nonce,
        expires_at=challenge.expires_at,
    )


@router.post("/apple", response_model=SignInResponse)
def authenticate_with_apple(
    request: AppleSignInRequest,
    db: Session = Depends(get_db),
    verifier: AppleTokenVerifier = Depends(get_apple_verifier),
) -> SignInResponse:
    try:
        identity = verifier.verify(
            request.identity_token,
            expected_nonce=request.nonce,
        )
    except AppleVerificationError as error:
        raise invalid_credentials() from error
    if not consume_auth_challenge(
        db,
        state=request.state,
        nonce=request.nonce,
    ):
        raise invalid_credentials()

    signed_in = sign_in_with_apple(
        db,
        identity=identity,
        provided_name=request.name,
        device=DeviceMetadata(**request.device.model_dump()),
    )
    return _sign_in_response(signed_in.user, signed_in.session)


@router.post("/dogfood", response_model=SignInResponse)
def authenticate_local_dogfood(
    request: DogfoodSignInRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(dogfood_bearer),
    db: Session = Depends(get_db),
) -> SignInResponse:
    if settings.app_env not in {"local", "test"} or not settings.allow_dogfood_auth:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    configured_token = settings.mobile_dogfood_token
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local dogfood authentication is not configured",
        )
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not compare_digest(credentials.credentials, configured_token)
    ):
        raise invalid_credentials()
    user = get_or_create_user_by_external_id(
        db,
        external_id=settings.mobile_dogfood_user_external_id,
    )
    signed_in = sign_in_for_local_dogfood(
        db,
        user=user,
        device=DeviceMetadata(**request.device.model_dump()),
    )
    return _sign_in_response(signed_in.user, signed_in.session)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh_session(
    request: RefreshSessionRequest,
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    try:
        session_pair = rotate_session(db, refresh_token=request.refresh_token)
    except AuthError as error:
        raise invalid_credentials() from error
    return _token_pair_response(session_pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> Response:
    revoke_session(db, access_token=authenticated.access_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
def revoke_every_session(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> Response:
    revoke_all_sessions(db, user=authenticated.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _sign_in_response(user, session_pair: SessionPair) -> SignInResponse:
    token_pair = _token_pair_response(session_pair)
    return SignInResponse(
        **token_pair.model_dump(),
        user=AuthenticatedUserResponse(
            public_id=user.public_id,
            name=user.name,
            email=user.email,
            timezone=user.timezone,
        ),
    )


def _token_pair_response(session_pair: SessionPair) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=session_pair.access_token,
        refresh_token=session_pair.refresh_token,
        access_expires_at=session_pair.access_expires_at,
        refresh_expires_at=session_pair.refresh_expires_at,
    )
