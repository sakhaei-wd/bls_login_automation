from __future__ import annotations

import logging
from typing import Mapping

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOGGER = logging.getLogger(__name__)


class BrowserSession:
    """Small wrapper around requests.Session with browser-like defaults."""

    def __init__(self, *, proxies: dict[str, str] | None, timeout: int) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.proxies.update(proxies or {})
        self.session.headers.update(default_headers())

        retry = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> requests.Response:
        LOGGER.info("GET %s", url)
        response = self.session.get(url, headers=dict(headers or {}), timeout=self.timeout)
        LOGGER.info("<- %s %s", response.status_code, response.url)
        return response

    def post(
        self,
        url: str,
        *,
        data: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> requests.Response:
        LOGGER.info("POST %s", url)
        response = self.session.post(
            url,
            data=data,
            headers=dict(headers or {}),
            timeout=self.timeout,
            allow_redirects=allow_redirects,
        )
        LOGGER.info("<- %s %s", response.status_code, response.url)
        return response


def default_headers() -> dict[str, str]:
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    }


def navigation_headers(*, referer: str | None = None) -> dict[str, str]:
    headers = {
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin" if referer else "none",
        "sec-fetch-user": "?1",
    }
    if referer:
        headers["referer"] = referer
    return headers


def form_headers(*, origin: str, referer: str) -> dict[str, str]:
    headers = navigation_headers(referer=referer)
    headers.update(
        {
            "content-type": "application/x-www-form-urlencoded",
            "origin": origin,
        }
    )
    return headers
