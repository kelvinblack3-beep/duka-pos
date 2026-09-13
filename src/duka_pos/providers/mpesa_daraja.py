"""M-Pesa Daraja provider: identity + OAuth + STK Push HTTP client.

M3.1 defined the DARAJA identity only.
M3.2 adds real HTTP against the current Safaricom Daraja contract:

  Sandbox base:  https://sandbox.safaricom.co.ke
  Production:    https://api.safaricom.co.ke

  OAuth:  GET  /oauth/v1/generate?grant_type=client_credentials
  STK:    POST /mpesa/stkpush/v1/processrequest

No inventory, sale, or stock logic lives here. Never open a SQLite transaction.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from duka_pos.daraja_config import DarajaConfig
from duka_pos.providers.base import ProviderInitiateResult

PROVIDER_NAME = "DARAJA"
_token_cache: dict[str, tuple[str, float]] = {}


class DarajaHttpError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpTransport(Protocol):
    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None,
        body: bytes | None = None, timeout: float = 30.0,
    ) -> tuple[int, bytes]: ...


class UrlLibTransport:
    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None,
        body: bytes | None = None, timeout: float = 30.0,
    ) -> tuple[int, bytes]:
        req = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return int(resp.status), resp.read()
        except HTTPError as exc:
            return int(exc.code), (exc.read() if hasattr(exc, "read") else b"")
        except URLError as exc:
            raise DarajaHttpError(f"network error: {exc}") from exc
