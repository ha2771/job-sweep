"""python -m jobsweep [--config config.toml] [--only greenhouse,ashby]"""

from __future__ import annotations

import argparse
import logging
import sys
import tomllib
from pathlib import Path

from .config import ConfigError, load_config
from .pipeline import ALL_SOURCES, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobsweep", description="Sweep public job-board APIs for fresh postings.")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--only", help=f"comma-separated subset of: {','.join(ALL_SOURCES)}")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("jobsweep")

    only = None
    if args.only:
        only = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = only - set(ALL_SOURCES)
        if unknown:
            log.error("unknown source(s): %s", ", ".join(sorted(unknown)))
            return 1
    try:
        cfg = load_config(args.config)
    except (ConfigError, OSError, tomllib.TOMLDecodeError) as exc:
        log.error("config: %s", exc)
        return 1
    _, code = run(cfg, only=only)
    if code:
        log.error("every source failed; see out/candidates.json 'sources' for errors")
    return code


if __name__ == "__main__":
    sys.exit(main())
