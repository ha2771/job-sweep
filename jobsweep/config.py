"""Load and validate config.toml. Everything in it ends up in URLs, so it is checked strictly."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discover import valid_token
from .sources.eightfold import Site
from .sources.workday import Tenant

_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$", re.I)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    window_hours: int
    user_agent: str
    max_workers: int
    per_host: int
    timeout: float
    state_path: Path
    out_dir: Path
    prune_days: int
    title_exclude: str
    title_include: str
    early_career: str
    role_noun: str
    include_role_noun: str
    discovery_enabled: bool
    discovery_include: bool
    discovery_max_age_days: int
    discovery_workday: bool
    discovery_workday_pages: int
    greenhouse: tuple[str, ...]
    ashby: tuple[str, ...]
    lever: tuple[str, ...]
    workday: tuple[Tenant, ...]
    eightfold: tuple[Site, ...]
    amazon_queries: tuple[str, ...]
    simplify_url: str | None


def _table(d: dict, key: str) -> dict:
    v = d.get(key, {})
    if not isinstance(v, dict):
        raise ConfigError(f"[{key}] must be a table")
    return v


def _get(d: dict, key: str, kind: type, default: Any, where: str) -> Any:
    v = d.get(key, default)
    if kind is float and isinstance(v, int) and not isinstance(v, bool):
        v = float(v)
    if not isinstance(v, kind) or (kind is int and isinstance(v, bool)):
        raise ConfigError(f"{where}.{key} must be {kind.__name__}")
    return v


def _strings(d: dict, key: str, where: str, *, tokens: bool = False) -> tuple[str, ...]:
    v = d.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ConfigError(f"{where}.{key} must be a list of strings")
    if tokens:
        bad = [x for x in v if not valid_token(x)]
        if bad:
            raise ConfigError(f"{where}.{key} has invalid board names: {bad}")
    return tuple(dict.fromkeys(x.strip() for x in v if x.strip()))


def _regex(d: dict, key: str, where: str) -> str:
    v = _get(d, key, str, None, where)
    try:
        re.compile(v)
    except re.error as exc:
        raise ConfigError(f"{where}.{key} is not a valid regex: {exc}") from None
    return v


def _host(v: Any, where: str) -> str:
    if not isinstance(v, str) or not _HOST.match(v):
        raise ConfigError(f"{where}: invalid host {v!r}")
    return v.lower()


def load_config(path: Path) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).resolve().parent
    run = _table(raw, "run")
    flt = _table(raw, "filters")
    disc = _table(raw, "discovery")

    tenants = []
    for i, t in enumerate(raw.get("workday", [])):
        where = f"workday[{i}]"
        if not isinstance(t, dict):
            raise ConfigError(f"{where} must be a table")
        site, tenant = _get(t, "site", str, None, where), _get(t, "tenant", str, None, where)
        if not valid_token(site) or not valid_token(tenant):
            raise ConfigError(f"{where}: invalid tenant/site")
        tenants.append(
            Tenant(
                company=_get(t, "company", str, None, where),
                host=_host(t.get("host"), where),
                tenant=tenant,
                site=site,
                queries=_strings(t, "queries", where) or ("",),
                max_pages=_get(t, "max_pages", int, 3, where),
            )
        )
    sites = []
    for i, s in enumerate(raw.get("eightfold", [])):
        where = f"eightfold[{i}]"
        if not isinstance(s, dict):
            raise ConfigError(f"{where} must be a table")
        sites.append(
            Site(
                company=_get(s, "company", str, None, where),
                host=_host(s.get("host"), where),
                domain=_host(s.get("domain"), where),
                queries=_strings(s, "queries", where) or ("",),
            )
        )
    simplify_url = _table(raw, "simplify").get("url")
    if simplify_url is not None and (not isinstance(simplify_url, str) or not simplify_url.startswith("https://")):
        raise ConfigError("simplify.url must be an https URL")

    window = _get(run, "window_hours", int, 72, "run")
    if not 1 <= window <= 24 * 14:
        raise ConfigError("run.window_hours must be between 1 and 336")
    return Config(
        window_hours=window,
        user_agent=_get(run, "user_agent", str, "job-sweep/0.1 (personal job search)", "run"),
        max_workers=max(1, min(64, _get(run, "max_workers", int, 16, "run"))),
        per_host=max(1, min(16, _get(run, "per_host_concurrency", int, 6, "run"))),
        timeout=_get(run, "timeout_seconds", float, 25.0, "run"),
        state_path=base / _get(run, "state_path", str, "out/state.json", "run"),
        out_dir=base / _get(run, "out_dir", str, "out", "run"),
        prune_days=_get(run, "prune_days", int, 45, "run"),
        title_exclude=_regex(flt, "title_exclude", "filters"),
        title_include=_regex(flt, "title_include", "filters"),
        early_career=_regex(flt, "early_career", "filters"),
        role_noun=_regex(flt, "role_noun", "filters"),
        include_role_noun=_regex(flt, "include_role_noun", "filters") if "include_role_noun" in flt else _regex(flt, "role_noun", "filters"),
        discovery_enabled=_get(disc, "enabled", bool, True, "discovery"),
        discovery_include=_get(disc, "include_in_sweep", bool, True, "discovery"),
        discovery_max_age_days=_get(disc, "max_age_days", int, 120, "discovery"),
        discovery_workday=_get(disc, "sweep_workday", bool, True, "discovery"),
        discovery_workday_pages=_get(disc, "workday_pages", int, 2, "discovery"),
        greenhouse=_strings(_table(raw, "greenhouse"), "tokens", "greenhouse", tokens=True),
        ashby=_strings(_table(raw, "ashby"), "boards", "ashby", tokens=True),
        lever=_strings(_table(raw, "lever"), "companies", "lever", tokens=True),
        workday=tuple(tenants),
        eightfold=tuple(sites),
        amazon_queries=_strings(_table(raw, "amazon"), "queries", "amazon"),
        simplify_url=simplify_url,
    )
