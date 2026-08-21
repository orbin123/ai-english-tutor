"""Delete aged local media cache files for the zero-cost Azure edition.

Retention defaults mirror docs/AZURE_ZERO_COST_MIGRATION.md:
  - learner/private audio: 7 days
  - TTS/public generated cache: 30 days

Blog media is intentionally excluded — posts may reference covers long-term.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def _purge_dir(root: Path, *, max_age_days: int, dry_run: bool) -> tuple[int, int]:
    if not root.exists():
        return 0, 0

    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0
    bytes_freed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        bytes_freed += path.stat().st_size
        deleted += 1
        if dry_run:
            logger.info("would delete %s", path)
        else:
            path.unlink(missing_ok=True)
    return deleted, bytes_freed


def run_cleanup(*, dry_run: bool = False) -> int:
    targets = [
        (Path(settings.STT_CACHE_DIR), settings.LEARNER_RECORDING_RETENTION_DAYS),
        (Path(settings.LEARNER_AUDIO_DIR), settings.LEARNER_RECORDING_RETENTION_DAYS),
        (Path(settings.PRONUNCIATION_CACHE_DIR), settings.LEARNER_RECORDING_RETENTION_DAYS),
        (Path(settings.TTS_CACHE_DIR), settings.TTS_CACHE_RETENTION_DAYS),
        (Path(settings.IMAGEGEN_CACHE_DIR), settings.TTS_CACHE_RETENTION_DAYS),
    ]
    total_deleted = 0
    total_bytes = 0
    for root, retention_days in targets:
        deleted, bytes_freed = _purge_dir(
            root,
            max_age_days=retention_days,
            dry_run=dry_run,
        )
        total_deleted += deleted
        total_bytes += bytes_freed
        logger.info(
            "blob_cleanup root=%s retention_days=%d deleted=%d bytes_freed=%d dry_run=%s",
            root,
            retention_days,
            deleted,
            bytes_freed,
            dry_run,
        )
    logger.info(
        "blob_cleanup_complete deleted=%d bytes_freed=%d dry_run=%s",
        total_deleted,
        total_bytes,
        dry_run,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log files that would be deleted without removing them.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run_cleanup(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
