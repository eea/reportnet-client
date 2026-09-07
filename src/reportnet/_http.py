from __future__ import annotations

import random
import re
import time
from typing import Any

import httpx

from ._log import get_logger
from .exceptions import APIError, AuthError, DatasetLockedError, RateLimitError

logger = get_logger(__name__)

_RETRYABLE_5XX = frozenset({500, 502, 503, 504})
_MAX_RETRIES = 3
_BASE_DELAY = 1.0

# Shapes a gateway-wrapped auth failure takes inside a 500 body. Confirmed
# live in two forms:
#   {"message":"status 403 reading JobControllerZuul#addImportJob(...)"}
#   ...an inner payload echoing "401"/UNAUTHORIZED
_WRAPPED_AUTH_RE = re.compile(
    r"""UNAUTHORIZED|FORBIDDEN"""      # inner status text
    r"""|["']40[13]["']"""             # "401" / '403' as a quoted token
    r"""|\bstatus["']?\s*[:=]?\s*40[13]\b""",  # status 403 / "status":401
    re.IGNORECASE,
)


def _backoff(attempt: int) -> float:
    return float(_BASE_DELAY * (2**attempt) + random.uniform(0, 0.1))


class HttpSession:
    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        api_key = api_key.strip() if api_key else api_key
        if not api_key:
            raise ValueError(
                "api_key must not be empty or whitespace-only; got "
                f"{api_key!r}. Check the value passed to ReportnetClient() "
                "or stored via reportnet.save_key()."
            )
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"ApiKey {api_key}"},
            timeout=timeout,
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("DELETE", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempt = 0
        while True:
            last_attempt = attempt >= _MAX_RETRIES
            logger.debug("%s %s", method, url)
            try:
                r = self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if last_attempt:
                    logger.warning(
                        "%s %s failed after %d attempts: %s", method, url, attempt + 1, exc
                    )
                    raise
                delay = _backoff(attempt)
                logger.warning(
                    "%s %s failed (%s); retrying in %.1fs (attempt %d/%d)",
                    method, url, exc, delay, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(delay)
                attempt += 1
                continue
            logger.debug("%s %s -> %d", method, url, r.status_code)
            # Only retry 5xx on GET — POST/PUT may have side effects.
            # Don't retry a 500 that is actually a wrapped auth failure.
            if (
                r.status_code in _RETRYABLE_5XX
                and method == "GET"
                and not last_attempt
                and not _is_wrapped_auth_500(r)
            ):
                delay = _backoff(attempt)
                logger.warning(
                    "%s %s returned %d; retrying in %.1fs (attempt %d/%d)",
                    method, url, r.status_code, delay, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(delay)
                attempt += 1
                continue
            _raise_for_status(r)
            return r

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpSession":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _is_wrapped_auth_500(response: httpx.Response) -> bool:
    """True if a 500 is actually a wrapped auth failure.

    The Reportnet gateway sometimes wraps auth failures as HTTP 500: the inner
    service returns 401 *or 403* and the gateway reports its own failure to
    read that response. Used both to raise AuthError instead of a generic
    APIError, and so the retry loop does not waste attempts on a permission
    error — must stay in sync between the two.

    403 matters as much as 401: a key with read but not write rights hits this
    on every import, and treating it as a transient 500 costs three retries
    with back-off before surfacing the wrong exception type.
    """
    if response.status_code != 500:
        return False
    return _WRAPPED_AUTH_RE.search(response.text) is not None


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise AuthError(response.status_code, response.text)
    if response.status_code == 423:
        raise DatasetLockedError(response.status_code, response.text)
    if response.status_code == 429:
        raise RateLimitError(response.status_code, response.text)
    if response.status_code >= 400:
        if _is_wrapped_auth_500(response):
            raise AuthError(response.status_code, response.text)
        raise APIError(response.status_code, response.text)
