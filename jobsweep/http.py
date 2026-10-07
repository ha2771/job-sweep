"""Small stdlib HTTP client: JSON in and out, retries with backoff, per-host concurrency caps.

Standard library only, so the workflow installs nothing at runtime.
"""

from __future__ import annotations

import http.client
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

MAX_BYTES = 64 * 1024 * 1024
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class HttpError(Exception):
    def __init__(self, url: str, status: int | None, detail: str = "") -> None:
        self.url = url
        self.status = status
        self.detail = detail
        super().__init__(self.short())

    def short(self) -> str:
        code = f"HTTP {self.status}" if self.status else "network error"
        return f"{code} {self.detail}".strip()


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, min(30.0, float(value)))
    except ValueError:
        return None


class Http:
    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float = 25.0,
        per_host: int = 6,
        retries: int = 3,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.per_host = per_host
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep
        self._sems: dict[str, threading.BoundedSemaphore] = {}
        self._lock = threading.Lock()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode(params, doseq=True)}"
        return self._request("GET", url, None)

    def post_json(self, url: str, body: Any) -> Any:
        return self._request("POST", url, json.dumps(body).encode("utf-8"))

    def _sem(self, url: str) -> threading.BoundedSemaphore:
        host = urllib.parse.urlsplit(url).netloc.lower()
        with self._lock:
            sem = self._sems.get(host)
            if sem is None:
                sem = self._sems[host] = threading.BoundedSemaphore(self.per_host)
            return sem

    def _request(self, method: str, url: str, data: bytes | None) -> Any:
        if not url.startswith("https://"):
            raise HttpError(url, None, "refusing non-https URL")
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        last = HttpError(url, None, "no attempt made")
        for attempt in range(self.retries + 1):
            wait: float | None = None
            with self._sem(url):
                try:
                    req = urllib.request.Request(url, data=data, headers=headers, method=method)
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 - scheme checked as https above
                        raw = resp.read(MAX_BYTES + 1)
                        status = resp.status
                    if len(raw) > MAX_BYTES:
                        raise HttpError(url, status, "response too large")
                    try:
                        return json.loads(raw)
                    except ValueError:
                        raise HttpError(url, status, "response was not JSON") from None
                except urllib.error.HTTPError as exc:
                    last = HttpError(url, exc.code, str(exc.reason))
                    if exc.code not in RETRY_STATUS:
                        raise last from None
                    wait = _retry_after(exc.headers.get("Retry-After") if exc.headers else None)
                except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
                    last = HttpError(url, None, type(exc).__name__)
            if attempt < self.retries:
                jitter = random.random()  # nosec B311 - retry jitter, not security
                self._sleep(wait if wait is not None else min(30.0, self.backoff**attempt + jitter))
        raise last
