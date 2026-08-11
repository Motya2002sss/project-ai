from dataclasses import dataclass
from secrets import compare_digest
from typing import Callable

import httpx
import jwt


APPLE_ISSUER = "https://appleid.apple.com"
ALLOWED_ALGORITHMS = {"RS256", "ES256"}


@dataclass(frozen=True)
class AppleIdentity:
    subject: str
    email: str | None
    email_verified: bool
    is_private_email: bool


class AppleVerificationError(ValueError):
    def __init__(self, reason: str = "invalid_identity_token"):
        self.reason = reason
        super().__init__(reason)


class AppleTokenVerifier:
    def __init__(
        self,
        *,
        client_id: str,
        jwks_url: str = "https://appleid.apple.com/auth/keys",
        jwks_provider: Callable[[], dict] | None = None,
    ):
        self.client_id = client_id
        self.jwks_url = jwks_url
        self.jwks_provider = jwks_provider or self._fetch_jwks

    def _fetch_jwks(self) -> dict:
        response = httpx.get(self.jwks_url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise AppleVerificationError()
        return payload

    def verify(self, identity_token: str, *, expected_nonce: str) -> AppleIdentity:
        try:
            header = jwt.get_unverified_header(identity_token)
            key_id = header.get("kid")
            algorithm = header.get("alg")
            if (
                not isinstance(key_id, str)
                or algorithm not in ALLOWED_ALGORITHMS
                or not expected_nonce
            ):
                raise AppleVerificationError()

            jwks = self.jwks_provider()
            keys = jwks.get("keys") if isinstance(jwks, dict) else None
            if not isinstance(keys, list):
                raise AppleVerificationError()
            matching_key = next(
                (
                    item
                    for item in keys
                    if isinstance(item, dict)
                    and item.get("kid") == key_id
                    and item.get("alg", algorithm) == algorithm
                ),
                None,
            )
            if matching_key is None:
                raise AppleVerificationError()

            signing_key = jwt.PyJWK.from_dict(matching_key).key
            claims = jwt.decode(
                identity_token,
                signing_key,
                algorithms=[algorithm],
                audience=self.client_id,
                issuer=APPLE_ISSUER,
                options={
                    "require": ["iss", "aud", "sub", "iat", "exp", "nonce"]
                },
            )
            nonce = claims.get("nonce")
            subject = claims.get("sub")
            if (
                not isinstance(nonce, str)
                or not compare_digest(nonce, expected_nonce)
                or not isinstance(subject, str)
                or not subject
            ):
                raise AppleVerificationError()
        except AppleVerificationError:
            raise
        except Exception as error:
            raise AppleVerificationError() from error

        email = claims.get("email")
        return AppleIdentity(
            subject=subject,
            email=email if isinstance(email, str) and email else None,
            email_verified=_claim_is_true(claims.get("email_verified")),
            is_private_email=_claim_is_true(claims.get("is_private_email")),
        )


def _claim_is_true(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")
