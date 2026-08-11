from typing import Literal
from urllib.parse import urlsplit

from app.core.config import Settings


RuntimeMode = Literal["local", "test", "staging", "production"]


class RuntimeConfigError(ValueError):
    def __init__(self, reasons: tuple[str, ...]):
        self.reasons = reasons
        super().__init__("Invalid runtime configuration: " + ", ".join(reasons))


def _uses_local_host(value: str) -> bool:
    hostname = urlsplit(value).hostname
    return hostname in {None, "localhost", "127.0.0.1", "::1"}


def validate_runtime_config(configured: Settings) -> None:
    if configured.app_env not in {"staging", "production"}:
        return

    reasons: list[str] = []
    if configured.app_debug:
        reasons.append("app_debug_must_be_false")
    if configured.allow_dogfood_auth or configured.mobile_dogfood_token:
        reasons.append("dogfood_auth_must_be_disabled")
    if _uses_local_host(configured.database_url):
        reasons.append("database_must_be_external")
    if (
        not configured.public_api_url
        or urlsplit(configured.public_api_url).scheme != "https"
        or _uses_local_host(configured.public_api_url)
    ):
        reasons.append("public_api_url_must_be_https")
    if not configured.apple_client_id:
        reasons.append("apple_client_id_is_required")
    if not configured.privacy_policy_url:
        reasons.append("privacy_policy_url_is_required")
    if not configured.terms_url:
        reasons.append("terms_url_is_required")
    if not configured.support_url:
        reasons.append("support_url_is_required")

    if reasons:
        raise RuntimeConfigError(tuple(reasons))
