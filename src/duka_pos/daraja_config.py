"""Daraja environment configuration (no secrets in code).

Required for live STK / OAuth when DARAJA_ENVIRONMENT is sandbox or production.
Tests inject a fake HTTP transport and never need real credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class DarajaConfigError(Exception):
    """Raised when required Daraja configuration is missing or invalid."""


@dataclass(frozen=True)
class DarajaConfig:
    consumer_key: str
    consumer_secret: str
    shortcode: str
    passkey: str
    callback_url: str
    environment: str  # "sandbox" | "production"
    timeout_seconds: float = 30.0

    @property
    def base_url(self) -> str:
        if self.environment == "production":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"

    @property
    def oauth_url(self) -> str:
        return f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"

    @property
    def stk_push_url(self) -> str:
        return f"{self.base_url}/mpesa/stkpush/v1/processrequest"

    @property
    def stk_query_url(self) -> str:
        return f"{self.base_url}/mpesa/stkpushquery/v1/query"


def load_daraja_config_from_env() -> DarajaConfig:
    """Load Daraja settings from environment. Raises if incomplete."""
    env = (os.environ.get("DARAJA_ENVIRONMENT") or "sandbox").strip().lower()
    if env not in ("sandbox", "production"):
        raise DarajaConfigError(
            f"DARAJA_ENVIRONMENT must be 'sandbox' or 'production', got {env!r}"
        )
    key = (os.environ.get("DARAJA_CONSUMER_KEY") or "").strip()
    secret = (os.environ.get("DARAJA_CONSUMER_SECRET") or "").strip()
    shortcode = (os.environ.get("DARAJA_SHORTCODE") or "").strip()
    passkey = (os.environ.get("DARAJA_PASSKEY") or "").strip()
    callback = (os.environ.get("DARAJA_CALLBACK_URL") or "").strip()
    if not all([key, secret, shortcode, passkey, callback]):
        raise DarajaConfigError(
            "Daraja requires DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET, "
            "DARAJA_SHORTCODE, DARAJA_PASSKEY, and DARAJA_CALLBACK_URL"
        )
    timeout_raw = os.environ.get("DARAJA_TIMEOUT_SECONDS", "30").strip()
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise DarajaConfigError("DARAJA_TIMEOUT_SECONDS must be a number") from exc
    if timeout <= 0 or timeout > 120:
        raise DarajaConfigError("DARAJA_TIMEOUT_SECONDS must be in (0, 120]")
    return DarajaConfig(
        consumer_key=key,
        consumer_secret=secret,
        shortcode=shortcode,
        passkey=passkey,
        callback_url=callback,
        environment=env,
        timeout_seconds=timeout,
    )
