from __future__ import annotations

import httpx

from .exceptions import APIError, AuthError


class HttpSession:
    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"ApiKey {api_key}"},
            timeout=timeout,
        )

    def get(self, url: str, **kwargs: object) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: object) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: object) -> httpx.Response:
        return self._request("PUT", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        response = self._client.request(method, url, **kwargs)
        _raise_for_status(response)
        return response

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpSession":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise AuthError(response.status_code, response.text)
    if response.status_code >= 400:
        raise APIError(response.status_code, response.text)
