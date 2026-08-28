from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure the tool's own log destination; source directories stay read-only."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("svg")
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        file_handler = logging.FileHandler(log_dir / "svg.log", encoding="utf-8")
    except FileNotFoundError:
        # A GUI scan may still be winding down while a temporary test/output
        # directory is cleaned up. Recreate only our configured log target
        # and retry once; source data paths are never touched here.
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "svg.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger
