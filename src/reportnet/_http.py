from __future__ import annotations

import random
import time
from typing import Any

import httpx

from .exceptions import APIError, AuthError, DatasetLockedError, RateLimitError

_RETRYABLE_5XX = frozenset({500, 502, 503, 504})
_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def _backoff(attempt: int) -> float:
    return float(_BASE_DELAY * (2**attempt) + random.uniform(0, 0.1))


class HttpSession:
    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
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
            try:
                r = self._client.request(method, url, **kwargs)
            except httpx.TransportError:
                if last_attempt:
                    raise
                time.sleep(_backoff(attempt))
                attempt += 1
                continue
            # Only retry 5xx on GET — POST/PUT may have side effects.
            # Don't retry a 500 that is actually a wrapped auth failure.
            is_auth_500 = r.status_code == 500 and "UNAUTHORIZED" in r.text
            if (
                r.status_code in _RETRYABLE_5XX
                and method == "GET"
                and not last_attempt
                and not is_auth_500
            ):
                time.sleep(_backoff(attempt))
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


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise AuthError(response.status_code, response.text)
    if response.status_code == 423:
        raise DatasetLockedError(response.status_code, response.text)
    if response.status_code == 429:
        raise RateLimitError(response.status_code, response.text)
    if response.status_code >= 400:
        # Reportnet gateway occasionally wraps auth failures as HTTP 500
        # (the inner service returns 401 but the gateway swallows it).
        # Detect this so callers see AuthError rather than a generic APIError,
        # and so the retry loop does not waste attempts on a bad API key.
        body = response.text
        if response.status_code == 500 and (
            "UNAUTHORIZED" in body or '"401"' in body or "'401'" in body
        ):
            raise AuthError(response.status_code, body)
        raise APIError(response.status_code, body)
