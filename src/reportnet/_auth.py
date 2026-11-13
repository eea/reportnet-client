"""Login-token (Keycloak bearer) authentication.

API keys cannot change a schema: on sandbox dataflow 11468 (2026-11-12) a
custodian API key got 403 on every schema write, while the same calls with the
user's login token returned 200. So the client supports a second credential.

The token endpoints are part of the transport, like the ``Authorization``
header in :mod:`reportnet._http`, which is why their URL shapes live here and
not in :class:`~reportnet.ReportnetClient`.

Secrets travel in **query strings** on these endpoints (the web app does the
same). The library never logs query strings itself, and :func:`_install_redaction`
masks them in httpx's own ``INFO`` request log, which would otherwise print
them in full.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Generator

import httpx

from ._log import get_logger
from .exceptions import AuthError, LoginTokenError

logger = get_logger(__name__)

REFRESH_PATH = "/user/refreshToken"
GENERATE_PATH = "/user/generateToken"

# Refresh this long before the access token expires.
_REFRESH_MARGIN_S = 60.0

_SECRET_QUERY_RE = re.compile(r"((?:refreshToken|password|code)=)[^&\s\"']+", re.IGNORECASE)
_WRAPPED_401_RE = re.compile(r"UNAUTHORIZED|[\"']401[\"']|\bstatus[\"']?\s*[:=]?\s*401\b", re.I)


@dataclass(frozen=True)
class TokenPair:
    """An access token and the refresh token that renews it.

    The refresh token **rotates**: every refresh returns a new one and the old
    one should be treated as spent. Persist the newest pair, never the first.
    """

    access_token: str
    refresh_token: str


class _RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(
                _SECRET_QUERY_RE.sub(r"\1***", str(a)) if isinstance(a, (str, httpx.URL)) else a
                for a in (record.args if isinstance(record.args, tuple) else (record.args,))
            )
        record.msg = _SECRET_QUERY_RE.sub(r"\1***", str(record.msg))
        return True


_REDACTION = _RedactSecrets()


def _install_redaction() -> None:
    """Mask token and password query values in httpx's request log (idempotent)."""
    for name in ("httpx", "reportnet"):
        log = logging.getLogger(name)
        if _REDACTION not in log.filters:
            log.addFilter(_REDACTION)


def redact(text: str) -> str:
    """Return *text* with token, password and code query values masked."""
    return _SECRET_QUERY_RE.sub(r"\1***", text)


def jwt_expiry(token: str) -> float | None:
    """Return the ``exp`` claim of a JWT as a POSIX timestamp, or None.

    The signature is **not** verified: the value is only used to decide when to
    refresh, and the server checks the token anyway.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
    except (ValueError, AttributeError):
        return None
    return float(exp) if isinstance(exp, (int, float)) else None


def _parse_token_response(response: httpx.Response) -> TokenPair:
    try:
        body = response.json()
        return TokenPair(str(body["accessToken"]), str(body["refreshToken"]))
    except (ValueError, KeyError, TypeError):
        raise AuthError(
            response.status_code,
            "token response did not contain accessToken and refreshToken",
        ) from None


def request_tokens(
    base_url: str, path: str, params: dict[str, str], *, timeout: float = 30.0
) -> TokenPair:
    """POST to a Reportnet token endpoint and return the new token pair.

    Raises :class:`LoginTokenError` on any non-2xx answer. The response body is
    not included in the error, since it may echo a secret.
    """
    _install_redaction()
    logger.debug("POST %s", path)
    with httpx.Client(base_url=base_url, timeout=timeout) as http:
        response = http.post(path, params=params)
    if response.status_code >= 400:
        raise LoginTokenError(response.status_code, path)
    return _parse_token_response(response)


def _is_auth_failure(response: httpx.Response) -> bool:
    if response.status_code == 401:
        return True
    if response.status_code == 500:
        return _WRAPPED_401_RE.search(response.text) is not None
    return False


class TokenAuth(httpx.Auth):
    """Send ``Authorization: Bearer <access token>`` and keep the token fresh.

    * Before a request, if the access token expires within 60 seconds (read
      from its JWT ``exp`` claim), it is refreshed first.
    * On a 401, or a gateway 500 that wraps one, it refreshes **once** and
      resends the request. Resending is safe: the server refused the request
      before acting on it.
    * The refresh token rotates; the newest pair is kept and passed to
      *on_refresh* so the caller can store it.
    * A lock stops two threads refreshing at the same time.

    Args:
        access_token: The ``accessToken`` from the web app's login session.
        refresh_token: The matching ``refreshToken``.
        base_url: API host that issues tokens.
        on_refresh: Called with the new :class:`TokenPair` after each refresh.
    """

    requires_request_body = True   # so a 401'd request can be sent again
    requires_response_body = True  # to recognise a 401 wrapped in a 500

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        *,
        base_url: str,
        on_refresh: Callable[[TokenPair], None] | None = None,
        timeout: float = 30.0,
    ) -> None:
        access_token = (access_token or "").strip()
        refresh_token = (refresh_token or "").strip()
        if not access_token or not refresh_token:
            raise ValueError("access_token and refresh_token must both be non-empty.")
        self._tokens = TokenPair(access_token, refresh_token)
        self._base_url = base_url
        self._on_refresh = on_refresh
        self._timeout = timeout
        self._lock = threading.Lock()
        _install_redaction()

    @property
    def tokens(self) -> TokenPair:
        """The current token pair, including the latest rotated refresh token."""
        return self._tokens

    def refresh(self) -> TokenPair:
        """Exchange the refresh token for a new pair now."""
        with self._lock:
            return self._refresh_locked()

    def _refresh_locked(self) -> TokenPair:
        logger.info("refreshing the Reportnet login token")
        pair = request_tokens(
            self._base_url,
            REFRESH_PATH,
            {"refreshToken": self._tokens.refresh_token},
            timeout=self._timeout,
        )
        self._tokens = pair
        if self._on_refresh is not None:
            self._on_refresh(pair)
        return pair

    def _expires_soon(self) -> bool:
        exp = jwt_expiry(self._tokens.access_token)
        return exp is not None and exp - time.time() < _REFRESH_MARGIN_S

    def _current_access(self) -> str:
        with self._lock:
            if self._expires_soon():
                self._refresh_locked()
            return self._tokens.access_token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        used = self._current_access()
        request.headers["Authorization"] = f"Bearer {used}"
        response = yield request
        if not _is_auth_failure(response):
            return
        with self._lock:
            # Another thread may already have refreshed while we waited.
            if self._tokens.access_token == used:
                self._refresh_locked()
            fresh = self._tokens.access_token
        logger.info("request was refused as unauthenticated; resending once with a new token")
        request.headers["Authorization"] = f"Bearer {fresh}"
        yield request

