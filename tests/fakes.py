"""A stand-in for Http that serves canned JSON by URL."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from jobsweep.http import HttpError


class FakeHttp:
    def __init__(self, routes: dict[str, Any], posts: dict[str, Any] | None = None) -> None:
        self.routes = routes
        self.posts = posts or {}
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        full = f"{url}?{urlencode(params, doseq=True)}" if params else url
        self.calls.append(full)
        for candidate in (full, url):
            if candidate in self.routes:
                value = self.routes[candidate]
                if isinstance(value, Exception):
                    raise value
                return value
        raise HttpError(url, 404, "Not Found")

    def post_json(self, url: str, body: Any) -> Any:
        self.calls.append(f"POST {url} {body}")
        handler = self.posts.get(url)
        if handler is None:
            raise HttpError(url, 404, "Not Found")
        return handler(body) if callable(handler) else handler
