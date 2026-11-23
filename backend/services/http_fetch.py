"""HTTP helpers shared by the source adapters: retries, timeouts, conditional GET."""

import time
from collections.abc import Iterator
from dataclasses import dataclass

import requests

USER_AGENT = "property-analyzer/0.1 (personal research tool)"
DEFAULT_TIMEOUT = 60


class SourceError(Exception):
    """A data source failed in a way the sync status should report."""


@dataclass
class ConditionalResult:
    unchanged: bool
    etag: str | None
    last_modified: str | None
    response: requests.Response | None


def get_json(url: str, params: dict | None = None, headers: dict | None = None, retries: int = 3) -> dict | list:
    response = _get_with_retries(url, params=params, headers=headers, retries=retries)
    try:
        return response.json()
    except ValueError as exc:
        raise SourceError(f"Non-JSON response from {url.split('?')[0]}") from exc


def get_text(url: str, params: dict | None = None, headers: dict | None = None, retries: int = 3) -> str:
    return _get_with_retries(url, params=params, headers=headers, retries=retries).text


def conditional_stream(url: str, etag: str | None, last_modified: str | None) -> ConditionalResult:
    """Open a streaming GET that returns unchanged=True when the server says 304 or the validators match."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    response = requests.get(url, headers=headers, stream=True, timeout=DEFAULT_TIMEOUT)
    new_etag = response.headers.get("ETag")
    new_last_modified = response.headers.get("Last-Modified")
    if response.status_code == 304 or (etag and new_etag == etag):
        response.close()
        return ConditionalResult(True, etag, last_modified, None)
    if response.status_code != 200:
        response.close()
        raise SourceError(f"HTTP {response.status_code} from {url}")
    return ConditionalResult(False, new_etag, new_last_modified, response)


def iter_lines(response: requests.Response) -> Iterator[str]:
    for line in response.iter_lines(decode_unicode=False, chunk_size=1 << 20):
        if line:
            yield line.decode("utf-8", errors="replace")


def _get_with_retries(url: str, params: dict | None, headers: dict | None = None, retries: int = 3) -> requests.Response:
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=merged_headers, timeout=DEFAULT_TIMEOUT)
            if response.status_code in (429, 500, 502, 503, 504):
                raise SourceError(f"HTTP {response.status_code}")
            if response.status_code != 200:
                raise SourceError(f"HTTP {response.status_code} from {url.split('?')[0]}")
            return response
        except (requests.RequestException, SourceError) as exc:
            last_error = exc
            if isinstance(exc, SourceError) and "HTTP 4" in str(exc) and "429" not in str(exc):
                break
            time.sleep(2 ** attempt)
    # requests exceptions embed the full URL, which can include API keys; report only the type.
    if isinstance(last_error, requests.RequestException):
        raise SourceError(f"{type(last_error).__name__} contacting {url.split('?')[0]}") from last_error
    raise SourceError(str(last_error)) from last_error
